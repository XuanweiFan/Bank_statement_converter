"""
Validation report data models
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class RuleViolation:
    """Single rule violation"""
    rule: str  # Rule name/ID
    severity: str  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    message: str
    row: Optional[int] = None
    field: Optional[str] = None
    expected: Optional[Any] = None
    actual: Optional[Any] = None
    difference: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'rule': self.rule,
            'severity': self.severity,
            'message': self.message,
            'row': self.row,
            'field': self.field,
            'expected': str(self.expected) if self.expected is not None else None,
            'actual': str(self.actual) if self.actual is not None else None,
            'difference': self.difference
        }


@dataclass
class ValidationReport:
    """Complete validation report"""
    document_id: str
    validation_status: str  # 'APPROVED', 'REVIEW_RECOMMENDED', 'NEEDS_REVIEW'
    
    # Risk signals (from Defense Layer 1)
    risk_signals: Optional[Dict[str, Any]] = None
    
    # Rule violations (from Defense Layer 2)
    rule_violations: List[RuleViolation] = field(default_factory=list)
    
    # Summary statistics
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    warnings: int = 0
    rule_pass_rate: float = 0.0

    # Confidence
    overall_confidence: float = 0.0
    confidence_label: str = "Low"
    confidence_components: List[Dict[str, Any]] = field(default_factory=list)
    confidence_notes: List[str] = field(default_factory=list)
    confidence_metrics: Dict[str, Any] = field(default_factory=dict)

    # Output artifacts
    output_files: Optional[Dict[str, str]] = None

    # Pattern matches
    pattern_matches: Optional[List[Dict[str, Any]]] = None
    
    def add_violation(self, violation: RuleViolation):
        """Add a rule violation"""
        self.rule_violations.append(violation)
        self.failed_checks += 1
    
    def add_violations(self, violations: List[RuleViolation]):
        """Add multiple rule violations"""
        self.rule_violations.extend(violations)
        self.failed_checks += len(violations)
    
    def calculate_summary(self):
        """Calculate summary statistics"""
        if self.total_checks == 0:
            self.total_checks = self.passed_checks + self.failed_checks
        else:
            minimum_total = self.passed_checks + self.failed_checks
            if self.total_checks < minimum_total:
                self.total_checks = minimum_total
        
        # Determine validation status
        critical_count = sum(1 for v in self.rule_violations if v.severity == 'CRITICAL')
        high_count = sum(1 for v in self.rule_violations if v.severity == 'HIGH')
        if critical_count > 0:
            self.validation_status = 'NEEDS_REVIEW'
        elif high_count > 0 or self.failed_checks > self.total_checks * 0.1:
            self.validation_status = 'REVIEW_RECOMMENDED'
        else:
            self.validation_status = 'APPROVED'
        
        # Calculate rule pass rate as a baseline confidence component
        if self.total_checks > 0:
            self.rule_pass_rate = self.passed_checks / self.total_checks
            if self.overall_confidence == 0.0:
                self.overall_confidence = self.rule_pass_rate
        else:
            self.rule_pass_rate = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export"""
        return {
            'document_id': self.document_id,
            'validation_status': self.validation_status,
            'summary': {
                'total_checks': self.total_checks,
                'passed_checks': self.passed_checks,
                'failed_checks': self.failed_checks,
                'warnings': self.warnings,
                'overall_confidence': self.overall_confidence,
                'rule_pass_rate': self.rule_pass_rate,
                'confidence_label': self.confidence_label
            },
            'confidence': {
                'score': self.overall_confidence,
                'label': self.confidence_label,
                'components': self.confidence_components,
                'notes': self.confidence_notes,
                'metrics': self.confidence_metrics
            },
            'risk_signals': self.risk_signals,
            'rule_violations': [v.to_dict() for v in self.rule_violations],
            'output_files': self.output_files,
            'pattern_matches': self.pattern_matches
        }
