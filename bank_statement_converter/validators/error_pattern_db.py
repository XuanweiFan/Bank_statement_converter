"""
Error Pattern Database
Detects known error patterns from accumulated experience
"""

import logging
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
import re
from decimal import Decimal

from ..models.ocr_result import OCRResult, TransactionRow

logger = logging.getLogger(__name__)


@dataclass
class ErrorPattern:
    """Single error pattern definition"""
    name: str
    description: str
    severity: str  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    field: str  # 'amount', 'date', 'description', etc.
    pattern_type: str  # 'regex', 'value_check', 'format_check'
    pattern_value: str  # Pattern to match (regex, format, etc.)
    fix_suggestion: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ErrorPattern':
        """Create from dictionary"""
        return cls(**data)


@dataclass
class PatternMatch:
    """Pattern match result"""
    pattern_name: str
    row: int
    field: str
    value: str
    severity: str
    message: str
    fix_suggestion: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class ErrorPatternDatabase:
    """
    Error pattern database for known OCR errors
    
    Features:
    - Pre-defined common patterns
    - Persistent storage (JSON)
    - Pattern matching
    - Feedback loop for new patterns
    """
    
    def __init__(self, pattern_file: str = None):
        default_path = Path(__file__).resolve().parents[1] / "config" / "error_patterns.json"
        self.pattern_file = Path(pattern_file) if pattern_file else default_path
        self.patterns: List[ErrorPattern] = []
        
        # Load patterns
        self.load_patterns()
        
        logger.info(f"Loaded {len(self.patterns)} error patterns")
    
    def match(self, result: OCRResult) -> List[PatternMatch]:
        """
        Match OCR result against all known patterns
        
        Returns:
            List of pattern matches
        """
        matches = []
        
        for row_idx, row in enumerate(result.rows):
            for pattern in self.patterns:
                pattern_matches = self._match_pattern(pattern, row, row_idx)
                matches.extend(pattern_matches)
        
        logger.info(f"Pattern matching: found {len(matches)} matches")
        return matches
    
    def _match_pattern(self, pattern: ErrorPattern, row: TransactionRow, row_idx: int) -> List[PatternMatch]:
        """Match single pattern against a row"""
        matches = []
        
        # Get field value
        field_value = self._get_field_value(row, pattern.field)
        if field_value is None:
            return matches
        
        # Match based on pattern type
        is_match = False
        
        if pattern.pattern_type == 'regex':
            is_match = bool(re.search(pattern.pattern_value, str(field_value)))
        
        elif pattern.pattern_type == 'format_check':
            is_match = self._check_format(str(field_value), pattern.pattern_value)
        
        elif pattern.pattern_type == 'value_check':
            is_match = self._check_value(field_value, pattern.pattern_value)
        
        if is_match:
            matches.append(PatternMatch(
                pattern_name=pattern.name,
                row=row_idx,
                field=pattern.field,
                value=str(field_value),
                severity=pattern.severity,
                message=f'{pattern.description}: {field_value}',
                fix_suggestion=pattern.fix_suggestion
            ))
        
        return matches
    
    def _get_field_value(self, row: TransactionRow, field: str) -> Optional[Any]:
        """Get field value from row"""
        field_map = {
            'amount': row.deposit if row.deposit is not None else row.withdrawal,
            'amount_raw': row.amount_raw,
            'date': row.transaction_date,
            'date_raw': row.date_raw,
            'description': row.description,
            'balance': row.balance
        }
        return field_map.get(field)
    
    def _check_format(self, value: str, format_type: str) -> bool:
        """Check if value matches a format"""
        format_checks = {
            'has_parentheses': lambda v: '(' in v and ')' in v,
            'missing_dollar_sign': lambda v: '$' not in v,
            'has_comma_as_decimal': lambda v: ',' in v and '.' not in v,
            'ambiguous_date': lambda v: bool(re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', v)),
            'has_letter_o': lambda v: 'O' in v.upper(),
            'has_letter_l': lambda v: 'l' in v.lower()
        }
        
        checker = format_checks.get(format_type)
        return checker(value) if checker else False
    
    def _check_value(self, value: Any, check_type: str) -> bool:
        """Check value properties"""
        if check_type == 'negative':
            return value < 0 if isinstance(value, (int, float, Decimal)) else False
        return False
    
    def load_patterns(self):
        """Load patterns from JSON file"""
        pattern_path = Path(self.pattern_file)
        
        if pattern_path.exists():
            try:
                with open(pattern_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.patterns = [ErrorPattern.from_dict(p) for p in data.get('patterns', [])]
                logger.info(f"Loaded {len(self.patterns)} patterns from {pattern_path}")
            except Exception as e:
                logger.error(f"Failed to load patterns: {e}")
                self.patterns = self._get_default_patterns()
        else:
            logger.info("No pattern file found, using defaults")
            self.patterns = self._get_default_patterns()
            self.save_patterns()
    
    def save_patterns(self):
        """Save patterns to JSON file"""
        pattern_path = Path(self.pattern_file)
        pattern_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'patterns': [p.to_dict() for p in self.patterns],
            'last_updated': datetime.now().isoformat(),
            'version': '1.0'
        }
        
        with open(pattern_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved {len(self.patterns)} patterns to {pattern_path}")
    
    def add_pattern(self, pattern: ErrorPattern):
        """Add new pattern and save"""
        self.patterns.append(pattern)
        self.save_patterns()
        logger.info(f"Added new pattern: {pattern.name}")
    
    def _get_default_patterns(self) -> List[ErrorPattern]:
        """Get default error patterns"""
        return [
            # Pattern 1: Bracket negative number misread
            ErrorPattern(
                name='bracket_negative_misread',
                description='Bracketed negative number possibly misread as positive',
                severity='HIGH',
                field='amount_raw',
                pattern_type='format_check',
                pattern_value='has_parentheses',
                fix_suggestion='Verify amount is negative'
            ),
            
            # Pattern 2: Missing dollar sign
            ErrorPattern(
                name='dollar_sign_missing',
                description='Amount missing dollar sign',
                severity='MEDIUM',
                field='amount_raw',
                pattern_type='format_check',
                pattern_value='missing_dollar_sign',
                fix_suggestion='Verify amount parsing'
            ),
            
            # Pattern 3: Comma as decimal point
            ErrorPattern(
                name='comma_decimal_confusion',
                description='Comma possibly misread as decimal point',
                severity='HIGH',
                field='amount_raw',
                pattern_type='format_check',
                pattern_value='has_comma_as_decimal',
                fix_suggestion='Check if European format (1.234,56)'
            ),
            
            # Pattern 4: Date ambiguity (MM/DD vs DD/MM)
            ErrorPattern(
                name='date_ambiguity',
                description='Date format ambiguous (MM/DD vs DD/MM)',
                severity='MEDIUM',
                field='date_raw',
                pattern_type='format_check',
                pattern_value='ambiguous_date',
                fix_suggestion='Verify month/day order'
            ),
            
            # Pattern 5: Letter O instead of zero
            ErrorPattern(
                name='zero_o_confusion',
                description='Letter O possibly confused with zero',
                severity='HIGH',
                field='amount_raw',
                pattern_type='format_check',
                pattern_value='has_letter_o',
                fix_suggestion='Check if O should be 0'
            ),
            
            # Pattern 6: Letter l instead of one
            ErrorPattern(
                name='one_l_confusion',
                description='Letter l possibly confused with 1',
                severity='HIGH',
                field='amount_raw',
                pattern_type='format_check',
                pattern_value='has_letter_l',
                fix_suggestion='Check if l should be 1'
            ),
            
            # Pattern 7: Negative deposit
            ErrorPattern(
                name='negative_deposit',
                description='Deposit amount is negative',
                severity='CRITICAL',
                field='amount',
                pattern_type='value_check',
                pattern_value='negative',
                fix_suggestion='Deposits should be positive'
            ),
        ]


class FeedbackLoop:
    """
    Feedback loop for continuous pattern improvement
    """
    
    def __init__(self, pattern_db: ErrorPatternDatabase):
        self.pattern_db = pattern_db
    
    def process_correction(self, document_id: str, row_idx: int, 
                          field: str, incorrect_value: str, correct_value: str,
                          description: str = ""):
        """
        Process a manual correction and potentially create new pattern
        
        Args:
            document_id: Document ID
            row_idx: Row index
            field: Field name
            incorrect_value: What OCR read
            correct_value: Correct value
            description: Error description
        """
        logger.info(f"Processing correction: {document_id} row {row_idx} field {field}")
        
        # Analyze error type
        error_type = self._analyze_error(incorrect_value, correct_value, field)
        
        # Check if similar pattern exists
        if not self._has_similar_pattern(error_type):
            # Create new pattern
            new_pattern = self._create_pattern_from_error(error_type, description)
            if new_pattern:
                self.pattern_db.add_pattern(new_pattern)
                logger.info(f"Created new pattern from feedback: {new_pattern.name}")
    
    def _analyze_error(self, incorrect: str, correct: str, field: str) -> Dict[str, Any]:
        """Analyze the type of error"""
        return {
            'field': field,
            'incorrect': incorrect,
            'correct': correct,
            'error_category': self._categorize_error(incorrect, correct)
        }
    
    def _categorize_error(self, incorrect: str, correct: str) -> str:
        """Categorize the error type"""
        # Simple categorization
        if '(' in incorrect or ')' in incorrect:
            return 'bracket_issue'
        elif incorrect.replace('O', '0') == correct:
            return 'o_zero_confusion'
        elif incorrect.replace('l', '1') == correct:
            return 'l_one_confusion'
        else:
            return 'other'
    
    def _has_similar_pattern(self, error_type: Dict) -> bool:
        """Check if similar pattern already exists"""
        category = error_type['error_category']
        return any(category in p.name for p in self.pattern_db.patterns)
    
    def _create_pattern_from_error(self, error_type: Dict, description: str) -> Optional[ErrorPattern]:
        """Create new pattern from error"""
        # Simplified - in production, use more sophisticated logic
        return None  # Placeholder
