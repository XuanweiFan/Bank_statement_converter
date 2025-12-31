"""
Confidence scoring and explainability layer.
"""

from __future__ import annotations

from typing import Dict, Any, List, Tuple, Optional

from ..models.ocr_result import OCRResult
from ..models.validation_report import ValidationReport
from .risk_signal_detector import ValidationConfig


class ConfidenceScorer:
    """
    Compute a composite confidence score with explainable components.
    """

    def __init__(self, config: ValidationConfig):
        self.config = config
        self.weights = dict(config.confidence_weights or {})

    def assess(self, primary: OCRResult, report: ValidationReport) -> Dict[str, Any]:
        components: List[Dict[str, Any]] = []
        metrics: Dict[str, Any] = {}
        notes: List[str] = []

        engine_score = self._engine_confidence(primary)
        metrics['engine_confidence'] = engine_score
        components.append(self._component(
            key='engine_quality',
            label='Primary engine quality',
            score=engine_score,
            weight=self.weights.get('engine_quality', 0.25),
            details={'source': 'Document AI page quality score'}
        ))

        completeness_score, coverage = self._field_completeness(primary)
        metrics['field_coverage'] = coverage
        components.append(self._component(
            key='field_completeness',
            label='Critical field coverage',
            score=completeness_score,
            weight=self.weights.get('field_completeness', 0.20),
            details=coverage
        ))

        rule_pass_rate = report.rule_pass_rate
        metrics['rule_pass_rate'] = rule_pass_rate
        components.append(self._component(
            key='rule_consistency',
            label='Hard-rule consistency',
            score=rule_pass_rate,
            weight=self.weights.get('rule_consistency', 0.25),
            details={
                'total_checks': report.total_checks,
                'failed_checks': report.failed_checks
            }
        ))

        risk_score, risk_details = self._risk_signal_score(report.risk_signals)
        metrics['risk_signals'] = risk_details
        components.append(self._component(
            key='risk_signals',
            label='Risk signal penalty',
            score=risk_score,
            weight=self.weights.get('risk_signals', 0.10),
            details=risk_details
        ))

        overall_score = self._weighted_score(components)
        label = self._label(overall_score)

        return {
            'score': overall_score,
            'label': label,
            'components': components,
            'metrics': metrics,
            'notes': notes
        }

    @staticmethod
    def _component(
        key: str,
        label: str,
        score: Optional[float],
        weight: float,
        details: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {
            'key': key,
            'label': label,
            'score': score,
            'weight': weight,
            'details': details,
            'available': score is not None
        }

    @staticmethod
    def _weighted_score(components: List[Dict[str, Any]]) -> float:
        usable = [c for c in components if c['available'] and c['weight'] > 0]
        total_weight = sum(c['weight'] for c in usable)
        if total_weight <= 0:
            return 0.0
        score = sum(c['score'] * c['weight'] for c in usable) / total_weight
        return max(0.0, min(1.0, score))

    @staticmethod
    def _label(score: float) -> str:
        if score >= 0.85:
            return "High"
        if score >= 0.7:
            return "Medium"
        return "Low"

    @staticmethod
    def _engine_confidence(result: OCRResult) -> float:
        if result.overall_confidence > 0:
            return result.overall_confidence

        confidences = []
        for row in result.rows:
            for value in (row.date_confidence, row.amount_confidence, row.balance_confidence):
                if value:
                    confidences.append(value)

        if not confidences:
            return 0.0
        return sum(confidences) / len(confidences)

    @staticmethod
    def _field_completeness(result: OCRResult) -> Tuple[float, Dict[str, float]]:
        if not result.rows:
            return 0.0, {
                'transaction_date': 0.0,
                'amount': 0.0,
                'balance': 0.0
            }

        total_rows = len(result.rows)
        date_count = sum(1 for row in result.rows if row.transaction_date)
        amount_count = sum(1 for row in result.rows if row.deposit is not None or row.withdrawal is not None)
        balance_count = sum(1 for row in result.rows if row.balance is not None)

        coverage = {
            'transaction_date': date_count / total_rows,
            'amount': amount_count / total_rows,
            'balance': balance_count / total_rows
        }

        score = sum(coverage.values()) / len(coverage)
        return score, coverage

    @staticmethod
    def _risk_signal_score(risk_signals: Optional[Dict[str, Any]]) -> Tuple[float, Dict[str, Any]]:
        counts = {
            'critical': 0,
            'high': 0,
            'medium': 0,
            'low': 0
        }
        if risk_signals:
            counts['critical'] = risk_signals.get('critical_count', 0)
            counts['high'] = risk_signals.get('high_count', 0)
            counts['medium'] = risk_signals.get('medium_count', 0)
            counts['low'] = risk_signals.get('low_count', 0)

        penalty = (
            counts['critical'] * 0.2 +
            counts['high'] * 0.1 +
            counts['medium'] * 0.05 +
            counts['low'] * 0.02
        )
        score = max(0.0, 1.0 - min(1.0, penalty))
        return score, {'counts': counts, 'penalty': penalty}
