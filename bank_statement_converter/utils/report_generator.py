"""
Report Generator
Generates CSV/Excel output and risk reports
"""

import logging
import json
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..models.ocr_result import OCRResult
from ..models.validation_report import ValidationReport

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Report Generator: Creates output files
    
    Outputs:
    1. CSV/Excel with transaction data
    2. JSON risk report
    """
    
    def __init__(self, output_dir: str = './output'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_csv(self, result: OCRResult, filename: str = None) -> str:
        """
        Generate CSV file from OCR result
        
        Returns:
            Path to generated CSV file
        """
        if filename is None:
            filename = f"{result.document_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        output_path = self.output_dir / filename
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'Transaction Date',
                'Description',
                'Deposit',
                'Withdrawal',
                'Balance',
                'Posting Date',
                'Reference',
                'Confidence (Date)',
                'Confidence (Amount)',
                'Confidence (Balance)'
            ])
            
            # Rows
            for row in result.rows:
                writer.writerow([
                    row.transaction_date,
                    row.description,
                    float(row.deposit) if row.deposit is not None else '',
                    float(row.withdrawal) if row.withdrawal is not None else '',
                    float(row.balance) if row.balance is not None else '',
                    row.posting_date if row.posting_date else '',
                    row.reference_number if row.reference_number else '',
                    f'{row.date_confidence:.2f}',
                    f'{row.amount_confidence:.2f}',
                    f'{row.balance_confidence:.2f}'
                ])
            
            # Summary rows
            writer.writerow([])
            writer.writerow(['Summary'])
            writer.writerow(['Opening Balance', '', '', '', 
                           float(result.opening_balance) if result.opening_balance is not None else ''])
            writer.writerow(['Closing Balance', '', '', '', 
                           float(result.closing_balance) if result.closing_balance is not None else ''])
            
            total_deposits = sum(float(r.deposit) for r in result.rows if r.deposit is not None)
            total_withdrawals = sum(float(r.withdrawal) for r in result.rows if r.withdrawal is not None)
            
            writer.writerow(['Total Deposits', '', float(total_deposits)])
            writer.writerow(['Total Withdrawals', '', '', float(total_withdrawals)])
        
        logger.info(f"CSV file generated: {output_path}")
        return str(output_path)
    
    def generate_risk_report(self, validation_report: ValidationReport, 
                            filename: str = None) -> str:
        """
        Generate JSON risk report
        
        Returns:
            Path to generated report file
        """
        if filename is None:
            filename = f"{validation_report.document_id}_risk_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        output_path = self.output_dir / filename
        
        # Create comprehensive report
        report_data = {
            'document_id': validation_report.document_id,
            'generated_at': datetime.now().isoformat(),
            'validation_status': validation_report.validation_status,
            'summary': {
                'total_checks': validation_report.total_checks,
                'passed_checks': validation_report.passed_checks,
                'failed_checks': validation_report.failed_checks,
                'warnings': validation_report.warnings,
                'overall_confidence': validation_report.overall_confidence,
                'rule_pass_rate': validation_report.rule_pass_rate,
                'confidence_label': validation_report.confidence_label
            },
            'confidence': {
                'score': validation_report.overall_confidence,
                'label': validation_report.confidence_label,
                'components': validation_report.confidence_components,
                'notes': validation_report.confidence_notes,
                'metrics': validation_report.confidence_metrics
            },
            'risk_signals': validation_report.risk_signals,
            'rule_violations': [v.to_dict() for v in validation_report.rule_violations],
            'pattern_matches': validation_report.pattern_matches,
            'recommendations': self._generate_recommendations(validation_report)
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Risk report generated: {output_path}")
        return str(output_path)

    def generate_review_rows_csv(self, result: OCRResult, validation_report: ValidationReport,
                                 filename: str = None) -> Optional[str]:
        """
        Generate CSV containing rows that require attention.
        """
        review_items = self._collect_review_items(validation_report)
        if not review_items:
            return None

        if filename is None:
            filename = f"{result.document_id}_review_rows_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        output_path = self.output_dir / filename

        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        review_items.sort(key=lambda item: severity_order.get(item.get("severity", "LOW"), 9))

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Row',
                'Source',
                'Field',
                'Severity',
                'Message',
                'Expected',
                'Actual'
            ])
            for item in review_items:
                writer.writerow([
                    item.get('row', ''),
                    item.get('source', ''),
                    item.get('field', ''),
                    item.get('severity', ''),
                    item.get('message', ''),
                    item.get('expected', ''),
                    item.get('actual', '')
                ])

        logger.info(f"Review rows CSV generated: {output_path}")
        return str(output_path)

    def generate_business_summary(self, result: OCRResult, validation_report: ValidationReport,
                                  elapsed_seconds: float, filename: str = None) -> str:
        """
        Generate a business-friendly JSON summary.
        """
        if filename is None:
            filename = f"{result.document_id}_business_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = self.output_dir / filename
        status = self._business_status(validation_report.validation_status)
        review_items = self._collect_review_items(validation_report)

        summary = {
            'document_id': validation_report.document_id,
            'generated_at': datetime.now().isoformat(),
            'processing_seconds': round(elapsed_seconds, 2),
            'status': status,
            'confidence': {
                'score': validation_report.overall_confidence,
                'label': validation_report.confidence_label
            },
            'counts': {
                'transactions': len(result.rows),
                'failed_checks': validation_report.failed_checks,
                'warnings': validation_report.warnings,
                'review_items': len(review_items)
            },
            'actions': self._business_actions(validation_report, review_items),
            'highlights': review_items[:10]
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"Business summary generated: {output_path}")
        return str(output_path)
    
    def _generate_recommendations(self, validation_report: ValidationReport) -> List[str]:
        """Generate actionable recommendations based on validation results"""
        recommendations = []
        
        if validation_report.validation_status == 'NEEDS_REVIEW':
            recommendations.append("CRITICAL: Manual review required before using this data")
        
        critical_violations = [v for v in validation_report.rule_violations 
                              if v.severity == 'CRITICAL']
        if critical_violations:
            recommendations.append(f"Found {len(critical_violations)} critical rule violations - "
                                 "verify data accuracy")
        
        if validation_report.confidence_label == 'Low':
            recommendations.append("Low confidence score - consider manual verification")
        
        if not recommendations:
            recommendations.append("Data passed all validations - safe to use")
        
        return recommendations

    def _collect_review_items(self, validation_report: ValidationReport) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []

        for violation in validation_report.rule_violations:
            items.append({
                'row': violation.row,
                'source': 'rule',
                'field': violation.field,
                'severity': violation.severity,
                'message': violation.message,
                'expected': str(violation.expected) if violation.expected is not None else '',
                'actual': str(violation.actual) if violation.actual is not None else ''
            })

        if validation_report.pattern_matches:
            for match in validation_report.pattern_matches:
                items.append({
                    'row': match.get('row'),
                    'source': 'pattern',
                    'field': match.get('field'),
                    'severity': match.get('severity'),
                    'message': match.get('message'),
                    'expected': '',
                    'actual': str(match.get('value', ''))
                })

        return items

    def _business_status(self, validation_status: str) -> Dict[str, str]:
        if validation_status == 'NEEDS_REVIEW':
            return {'label': 'Needs Review', 'risk_level': 'High'}
        if validation_status == 'REVIEW_RECOMMENDED':
            return {'label': 'Review Recommended', 'risk_level': 'Medium'}
        if validation_status == 'APPROVED':
            return {'label': 'Approved', 'risk_level': 'Low'}
        return {'label': validation_status, 'risk_level': 'Unknown'}

    def _business_actions(self, validation_report: ValidationReport,
                          review_items: List[Dict[str, Any]]) -> List[str]:
        actions = []

        if validation_report.validation_status == 'NEEDS_REVIEW':
            actions.append("Manual review required before use")
        elif validation_report.validation_status == 'REVIEW_RECOMMENDED':
            actions.append("Manual spot-check recommended")
        else:
            actions.append("Data looks usable; perform standard spot-check")

        if review_items:
            actions.append("Review the generated review_rows CSV for flagged items")

        return actions
    
    def generate_summary_report(self, result: OCRResult, validation_report: ValidationReport) -> str:
        """
        Generate human-readable summary report
        
        Returns:
            Formatted text report
        """
        lines = []
        lines.append("=" * 80)
        lines.append("BANK STATEMENT PROCESSING REPORT")
        lines.append("=" * 80)
        lines.append(f"Document ID: {result.document_id}")
        lines.append(f"Processed: {result.processed_at}")
        lines.append(f"Primary Engine: {result.engine}")
        lines.append("")
        
        lines.append("VALIDATION STATUS")
        lines.append("-" * 80)
        lines.append(f"Status: {validation_report.validation_status}")
        lines.append(
            f"Confidence Score: {validation_report.overall_confidence:.1%} "
            f"({validation_report.confidence_label})"
        )
        lines.append(f"Rule Pass Rate: {validation_report.rule_pass_rate:.1%}")
        lines.append("")
        
        lines.append("STATISTICS")
        lines.append("-" * 80)
        lines.append(f"Total Transactions: {len(result.rows)}")
        lines.append(f"Total Checks: {validation_report.total_checks}")
        lines.append(f"Passed: {validation_report.passed_checks}")
        lines.append(f"Failed: {validation_report.failed_checks}")
        lines.append(f"Warnings: {validation_report.warnings}")
        lines.append("")
        
        if validation_report.risk_signals:
            lines.append("RISK SIGNALS")
            lines.append("-" * 80)
            for signal in validation_report.risk_signals.get('signals', []):
                lines.append(f"  [{signal['severity']}] {signal['type']}: {signal['message']}")
            lines.append("")

        if validation_report.confidence_components:
            lines.append("CONFIDENCE BREAKDOWN")
            lines.append("-" * 80)
            for component in validation_report.confidence_components:
                if component.get('available') and component.get('score') is not None:
                    lines.append(
                        f"  {component['label']}: {component['score']:.1%} "
                        f"(weight {component['weight']:.2f})"
                    )
            lines.append("")
        
        if validation_report.rule_violations:
            lines.append("RULE VIOLATIONS")
            lines.append("-" * 80)
            for violation in validation_report.rule_violations[:10]:  # Limit to 10
                lines.append(f"  [{violation.severity}] Row {violation.row}: {violation.message}")
            if len(validation_report.rule_violations) > 10:
                lines.append(f"  ... and {len(validation_report.rule_violations) - 10} more violations")
            lines.append("")

        if validation_report.pattern_matches:
            lines.append("ERROR PATTERN MATCHES")
            lines.append("-" * 80)
            for match in validation_report.pattern_matches[:10]:
                lines.append(
                    f"  [{match.get('severity', 'MEDIUM')}] Row {match.get('row')}: {match.get('message')}"
                )
            if len(validation_report.pattern_matches) > 10:
                lines.append(f"  ... and {len(validation_report.pattern_matches) - 10} more pattern matches")
            lines.append("")
        
        lines.append("RECOMMENDATIONS")
        lines.append("-" * 80)
        for rec in self._generate_recommendations(validation_report):
            lines.append(f"  • {rec}")
        lines.append("")
        lines.append("=" * 80)
        
        return '\n'.join(lines)
