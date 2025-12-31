"""
OCR Result data models
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import date
from decimal import Decimal


@dataclass
class BoundingBox:
    """Bounding box coordinates"""
    x: float
    y: float
    width: float
    height: float


@dataclass
class TransactionRow:
    """Single transaction record"""
    # Core fields
    transaction_date: Optional[date]
    description: str
    deposit: Optional[Decimal] = None
    withdrawal: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    
    # Optional fields
    posting_date: Optional[date] = None
    reference_number: Optional[str] = None
    
    # Confidence scores
    date_confidence: float = 0.0
    description_confidence: float = 0.0
    amount_confidence: float = 0.0
    balance_confidence: float = 0.0
    
    # Metadata
    bbox: Optional[BoundingBox] = None
    page_number: int = 1
    row_index: int = 0
    
    # Raw OCR text (for error pattern matching)
    amount_raw: str = ""
    date_raw: str = ""


@dataclass
class OCRResult:
    """Complete OCR result from one engine"""
    # Document metadata
    document_id: str
    engine: str  # 'document_ai'
    processed_at: str
    
    # Table data
    rows: List[TransactionRow] = field(default_factory=list)
    
    # Header detection
    header: List[str] = field(default_factory=list)
    header_detected: bool = False
    header_confidence: float = 0.0
    
    # Balance information
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    
    # Document info
    page_count: int = 1
    total_rows: int = 0
    
    # Overall confidence
    overall_confidence: float = 0.0


@dataclass
class RiskSignal:
    """Single risk signal"""
    signal_type: str  # 'LOW_CONFIDENCE', 'STRUCTURAL_ANOMALY', 'LOGIC_FAILURE', 'UNKNOWN_TEMPLATE'
    severity: str  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    details: Dict[str, Any] = field(default_factory=dict)
    action: str = 'LOG_ONLY'  # 'LOG_ONLY', 'REVIEW_RECOMMENDED', 'MANUAL_REVIEW'
    message: str = ""


@dataclass
class RiskSignals:
    """Collection of risk signals"""
    signals: List[RiskSignal] = field(default_factory=list)
    
    def add(self, signal_type: str, details: Dict[str, Any]):
        """Add a new risk signal"""
        signal = RiskSignal(
            signal_type=signal_type,
            severity=details.get('severity', 'MEDIUM'),
            details=details,
            action=details.get('action', 'LOG_ONLY'),
            message=details.get('message', '')
        )
        self.signals.append(signal)
    
    def has_critical(self) -> bool:
        """Check if any CRITICAL signals exist"""
        return any(s.severity == 'CRITICAL' for s in self.signals)
    
    def count_high_or_medium(self) -> int:
        """Count HIGH or MEDIUM severity signals"""
        return sum(1 for s in self.signals if s.severity in ['HIGH', 'MEDIUM'])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for reporting"""
        return {
            'total_signals': len(self.signals),
            'critical_count': sum(1 for s in self.signals if s.severity == 'CRITICAL'),
            'high_count': sum(1 for s in self.signals if s.severity == 'HIGH'),
            'medium_count': sum(1 for s in self.signals if s.severity == 'MEDIUM'),
            'low_count': sum(1 for s in self.signals if s.severity == 'LOW'),
            'signals': [
                {
                    'type': s.signal_type,
                    'severity': s.severity,
                    'message': s.message,
                    'action': s.action,
                    'details': s.details
                }
                for s in self.signals
            ]
        }
