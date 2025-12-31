"""
Defense Layer 1: Risk Signal Detector
Detects risk signals for review guidance and confidence scoring.
"""

import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field
from decimal import Decimal

from ..models.ocr_result import OCRResult, RiskSignals

logger = logging.getLogger(__name__)


@dataclass
class ValidationConfig:
    """Validation configuration"""
    confidence_threshold: float = 0.85
    field_coverage_thresholds: Dict[str, float] = field(default_factory=lambda: {
        'transaction_date': 0.95,
        'amount': 0.90,
        'balance': 0.85
    })
    confidence_weights: Dict[str, float] = field(default_factory=lambda: {
        'engine_quality': 0.30,
        'field_completeness': 0.25,
        'rule_consistency': 0.30,
        'risk_signals': 0.15
    })
    trigger_rules: Dict[str, bool] = field(default_factory=lambda: {
        'low_confidence': True,
        'low_coverage': True,
        'structural_anomaly': True,
        'logic_failure': True,
        'unknown_template': True
    })


class RiskSignalDetector:
    """
    Risk Signal Detector: surfaces signals for review guidance.
    
    5 types of risk signals:
    1. Low confidence in key fields
    2. Low field coverage (missing critical fields)
    3. Structural anomalies
    4. Logic failures (quick check)
    5. Unknown template
    """
    
    def __init__(self, config: ValidationConfig = None):
        self.config = config or ValidationConfig()
        self.confidence_threshold = self.config.confidence_threshold
        
        # Known Canadian banks
        self.known_banks = {
            'RBC': ['Royal Bank', 'RBC', 'Royal'],
            'TD': ['TD Bank', 'Toronto-Dominion', 'TD Canada'],
            'BMO': ['Bank of Montreal', 'BMO', 'BMO Bank'],
            'Scotiabank': ['Scotiabank', 'Scotia', 'Bank of Nova Scotia'],
            'CIBC': ['CIBC', 'Canadian Imperial', 'Imperial Bank']
        }
    
    def detect_signals(self, docai_result: OCRResult) -> RiskSignals:
        """
        Detect all risk signals
        
        Returns:
            RiskSignals object with all detected signals
        """
        signals = RiskSignals()
        
        logger.info(f"Detecting risk signals for document {docai_result.document_id}")

        if not docai_result.rows:
            signals.add('NO_ROWS', {
                'severity': 'CRITICAL',
                'action': 'MANUAL_REVIEW',
                'message': 'No transaction rows extracted'
            })
            logger.error("NO_ROWS signal: no transactions extracted")
            return signals
        
        # Signal 1: Low confidence in key fields
        if self.config.trigger_rules.get('low_confidence', True):
            low_conf_fields = self.check_low_confidence(docai_result)
            if low_conf_fields:
                signals.add('LOW_CONFIDENCE', {
                    'fields': low_conf_fields,
                    'severity': 'HIGH',
                    'action': 'REVIEW_RECOMMENDED',
                    'message': f"Found {len(low_conf_fields)} low confidence fields"
                })
                logger.warning(f"LOW_CONFIDENCE signal: {len(low_conf_fields)} fields")
        
        # Signal 2: Structural anomalies
        if self.config.trigger_rules.get('low_coverage', True):
            coverage_issue = self.check_field_coverage(docai_result)
            if coverage_issue:
                signals.add('LOW_FIELD_COVERAGE', coverage_issue)
                logger.warning("LOW_FIELD_COVERAGE signal detected")

        # Signal 3: Structural anomalies
        if self.config.trigger_rules.get('structural_anomaly', True):
            structural_issues = self.check_structural_anomaly(docai_result)
            if structural_issues:
                signals.add('STRUCTURAL_ANOMALY', {
                    'issues': structural_issues,
                    'severity': 'MEDIUM',
                    'action': 'REVIEW_RECOMMENDED',
                    'message': f"Detected {len(structural_issues)} structural issues"
                })
                logger.warning(f"STRUCTURAL_ANOMALY signal: {len(structural_issues)} issues")
        
        # Signal 4: Logic failures (quick check)
        if self.config.trigger_rules.get('logic_failure', True):
            logic_errors = self.quick_logic_check(docai_result)
            if logic_errors:
                signals.add('LOGIC_FAILURE', {
                    'errors': logic_errors,
                    'severity': 'CRITICAL',
                    'action': 'MANUAL_REVIEW',
                    'message': f"Detected {len(logic_errors)} logic errors"
                })
                logger.error(f"LOGIC_FAILURE signal: {len(logic_errors)} errors")
        
        # Signal 5: Unknown template
        if self.config.trigger_rules.get('unknown_template', True):
            template_confidence = self.detect_bank_template(docai_result)
            if template_confidence < 0.7:
                signals.add('UNKNOWN_TEMPLATE', {
                    'confidence': template_confidence,
                    'severity': 'MEDIUM',
                    'action': 'REVIEW_RECOMMENDED',
                    'message': f"Unknown bank template (confidence: {template_confidence:.2f})"
                })
                logger.warning(f"UNKNOWN_TEMPLATE signal: confidence={template_confidence:.2f}")
        
        logger.info(f"Risk signal detection complete: {len(signals.signals)} signals detected")
        return signals
    
    def check_low_confidence(self, result: OCRResult) -> List[Dict]:
        """
        Signal 1: Check for low confidence in key fields
        
        Priority levels:
        - P0 (Critical): amount, balance
        - P1 (High): transaction_date
        - P2 (Medium): description, posting_date
        
        Trigger conditions:
        - Any P0 field with confidence < threshold
        - More than 20% of P1 fields with confidence < threshold
        """
        low_conf_fields = []
        
        for row_idx, row in enumerate(result.rows):
            # P0 fields: amount and balance
            if row.amount_confidence < self.confidence_threshold:
                low_conf_fields.append({
                    'row': row_idx,
                    'field': 'amount',
                    'confidence': row.amount_confidence,
                    'priority': 'P0'
                })
            
            if row.balance_confidence < self.confidence_threshold:
                low_conf_fields.append({
                    'row': row_idx,
                    'field': 'balance',
                    'confidence': row.balance_confidence,
                    'priority': 'P0'
                })
            
            # P1 field: transaction date
            if row.date_confidence < self.confidence_threshold:
                low_conf_fields.append({
                    'row': row_idx,
                    'field': 'transaction_date',
                    'confidence': row.date_confidence,
                    'priority': 'P1'
                })
        
        # Trigger conditions
        p0_count = sum(1 for f in low_conf_fields if f['priority'] == 'P0')
        p1_count = sum(1 for f in low_conf_fields if f['priority'] == 'P1')
        p1_rate = p1_count / len(result.rows) if result.rows else 0
        
        # Trigger if: any P0 field OR more than 20% of P1 fields
        if p0_count > 0 or p1_rate > 0.2:
            return low_conf_fields
        
        return []

    def check_field_coverage(self, result: OCRResult) -> Dict[str, Any]:
        """
        Signal: Low field coverage (missing critical fields).
        """
        if not result.rows:
            return {}

        total_rows = len(result.rows)
        missing_date = [i for i, row in enumerate(result.rows) if not row.transaction_date]
        missing_amount = [
            i for i, row in enumerate(result.rows)
            if row.deposit is None and row.withdrawal is None
        ]
        missing_balance = [i for i, row in enumerate(result.rows) if row.balance is None]

        coverage = {
            'transaction_date': 1 - (len(missing_date) / total_rows),
            'amount': 1 - (len(missing_amount) / total_rows),
            'balance': 1 - (len(missing_balance) / total_rows)
        }

        thresholds = self.config.field_coverage_thresholds
        below = {
            field: coverage[field]
            for field in coverage
            if coverage[field] < thresholds.get(field, 0.0)
        }

        if not below:
            return {}

        severity = 'HIGH' if any(score < 0.7 for score in below.values()) else 'MEDIUM'
        return {
            'severity': severity,
            'action': 'REVIEW_RECOMMENDED',
            'message': 'Low coverage for critical fields',
            'coverage': coverage,
            'missing_examples': {
                'transaction_date': missing_date[:10],
                'amount': missing_amount[:10],
                'balance': missing_balance[:10]
            }
        }
    
    def check_structural_anomaly(self, result: OCRResult) -> List[Dict]:
        """
        Signal 2: Check for structural anomalies
        
        Checks:
        - Inconsistent column counts across rows
        - Row splitting failures (abnormal row heights)
        - Cross-page table breaks
        - Header detection failure
        """
        issues = []
        
        # Skip if not enough data
        if len(result.rows) < 3:
            return issues
        
        # Check 1: Column count consistency (simplified - checking row data completeness)
        incomplete_rows = []
        for idx, row in enumerate(result.rows):
            # Count missing critical fields
            missing_count = sum([
                row.transaction_date is None,
                row.balance is None,
                row.deposit is None and row.withdrawal is None
            ])
            if missing_count >= 2:  # More than 1 critical field missing
                incomplete_rows.append(idx)
        
        if len(incomplete_rows) > len(result.rows) * 0.1:  # More than 10% incomplete
            issues.append({
                'type': 'INCONSISTENT_ROWS',
                'details': f'{len(incomplete_rows)} rows have incomplete data',
                'rows': incomplete_rows[:10]  # Limit to first 10
            })
        
        # Check 2: Header detection
        if not result.header_detected or result.header_confidence < 0.7:
            issues.append({
                'type': 'HEADER_DETECTION_FAILURE',
                'details': 'Header not detected or low confidence',
                'header_confidence': result.header_confidence
            })
        
        # Check 3: Cross-page issues (if multi-page)
        if result.page_count > 1:
            # Simple check: look for large gaps in row indices
            page_transitions = [i for i in range(1, len(result.rows)) 
                              if result.rows[i].page_number != result.rows[i-1].page_number]
            
            if len(page_transitions) > 0:
                issues.append({
                    'type': 'MULTI_PAGE_DOCUMENT',
                    'details': f'Document spans {result.page_count} pages',
                    'page_transitions': page_transitions
                })
        
        return issues
    
    def quick_logic_check(self, result: OCRResult) -> List[Dict]:
        """
        Signal 3: Quick logic check (simplified)
        
        Quick checks:
        1. Overall balance check (±10% tolerance)
        2. Date range anomaly
        3. Negative amounts in wrong fields
        """
        errors = []
        
        # Quick check 1: Overall balance (if available)
        if result.opening_balance is not None and result.closing_balance is not None and result.rows:
            total_deposits = sum(
                (r.deposit for r in result.rows if r.deposit is not None),
                Decimal('0')
            )
            total_withdrawals = sum(
                (r.withdrawal for r in result.rows if r.withdrawal is not None),
                Decimal('0')
            )
            
            expected_closing = result.opening_balance + total_deposits - total_withdrawals
            actual_closing = result.closing_balance
            
            if actual_closing != 0:
                diff_rate = abs(expected_closing - actual_closing) / abs(actual_closing)
                
                if diff_rate > 0.1:  # More than 10% difference
                    errors.append({
                        'type': 'BALANCE_MISMATCH',
                        'expected': float(expected_closing),
                        'actual': float(actual_closing),
                        'diff_rate': diff_rate
                    })
        
        # Quick check 2: Date range
        dates = [r.transaction_date for r in result.rows if r.transaction_date]
        if dates:
            date_span = (max(dates) - min(dates)).days
            
            if date_span > 400:  # More than 13 months
                errors.append({
                    'type': 'DATE_RANGE_ANOMALY',
                    'span_days': date_span,
                    'min_date': str(min(dates)),
                    'max_date': str(max(dates))
                })
        
        # Quick check 3: Negative amounts
        for idx, row in enumerate(result.rows):
            if row.deposit is not None and row.deposit < 0:
                errors.append({
                    'type': 'NEGATIVE_DEPOSIT',
                    'row': idx,
                    'value': float(row.deposit)
                })
            
            if row.withdrawal is not None and row.withdrawal < 0:
                errors.append({
                    'type': 'NEGATIVE_WITHDRAWAL',
                    'row': idx,
                    'value': float(row.withdrawal)
                })
        
        return errors
    
    def detect_bank_template(self, result: OCRResult) -> float:
        """
        Signal 4: Bank template detection
        
        Returns confidence score (0-1) for template recognition
        """
        if not result.rows:
            return 0.0
        
        # Sample text from first few rows
        text_sample = ' '.join([row.description for row in result.rows[:5] if row.description])
        text_sample_lower = text_sample.lower()
        
        # Check for known bank keywords
        for bank, keywords in self.known_banks.items():
            if any(kw.lower() in text_sample_lower for kw in keywords):
                logger.info(f"Detected bank template: {bank}")
                return 0.9  # High confidence
        
        # Check header
        if result.header:
            header_text = ' '.join(result.header).lower()
            for bank, keywords in self.known_banks.items():
                if any(kw.lower() in header_text for kw in keywords):
                    logger.info(f"Detected bank template from header: {bank}")
                    return 0.85
        
        logger.warning("Unknown bank template")
        return 0.3  # Unknown template
    
