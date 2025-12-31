"""
Main processing pipeline
Integrates all defense layers
"""

import logging
from typing import Optional, Tuple
from pathlib import Path
import asyncio
from dataclasses import dataclass, field
import time
import mimetypes

from .document_ai_client import DocumentAIClient, DocumentAIConfig
from ..validators import RiskSignalDetector, HardRulesValidator, ValidationConfig, ConfidenceScorer
from ..validators.error_pattern_db import ErrorPatternDatabase, FeedbackLoop
from ..models.ocr_result import OCRResult
from ..models.validation_report import ValidationReport
from ..utils.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Pipeline configuration"""
    docai_config: Optional[DocumentAIConfig] = None
    validation_config: ValidationConfig = field(default_factory=ValidationConfig)
    output_dir: str = './output'
    force_manual_review: bool = True
    emit_summary: bool = True


class BankStatementPipeline:
    """
    Main processing pipeline for bank statements
    
    Two-layer defense architecture:
    1. Defense Layer 1: Risk signal detection
    2. Defense Layer 2: Hard rules + soft rules + error patterns
    """
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        
        # Initialize OCR clients
        if config.docai_config:
            self.docai_client = DocumentAIClient(config.docai_config)
        else:
            self.docai_client = None
            logger.warning("Document AI not configured")
        
        # Initialize validators
        self.risk_detector = RiskSignalDetector(config.validation_config)
        self.hard_rules = HardRulesValidator()
        self.error_pattern_db = ErrorPatternDatabase()
        self.feedback_loop = FeedbackLoop(self.error_pattern_db)
        self.confidence_scorer = ConfidenceScorer(config.validation_config)
        
        # Initialize report generator
        self.report_gen = ReportGenerator(config.output_dir)
        
        logger.info("Pipeline initialized")
    
    async def process(self, pdf_path: str) -> Tuple[OCRResult, ValidationReport]:
        """
        Process a bank statement PDF
        
        Returns:
            (OCRResult, ValidationReport)
        """
        logger.info(f"Processing: {pdf_path}")
        start_time = time.monotonic()
        
        # Read PDF
        pdf_file = Path(pdf_path)
        if not pdf_file.exists() or not pdf_file.is_file():
            raise FileNotFoundError(f"Input file not found: {pdf_path}")

        pdf_bytes = pdf_file.read_bytes()
        
        # Step 1: Process with primary engine (Document AI)
        logger.info("=" * 80)
        logger.info("DEFENSE LAYER 1: Primary Engine Processing + Risk Detection")
        logger.info("=" * 80)
        
        if not self.docai_client:
            raise ValueError("Document AI client not configured")
        
        mime_type, _ = mimetypes.guess_type(str(pdf_file))
        if not mime_type:
            mime_type = "application/pdf"
        primary_result = await self.docai_client.process_document(pdf_bytes, mime_type=mime_type)
        logger.info(f"Primary engine extracted {len(primary_result.rows)} rows")
        
        # Step 2: Risk signal detection
        risk_signals = self.risk_detector.detect_signals(primary_result)
        logger.info(f"Risk signals: {len(risk_signals.signals)}")
        
        # Step 3: Hard rules validation
        logger.info("=" * 80)
        logger.info("DEFENSE LAYER 2: Enhanced Logic Detection")
        logger.info("=" * 80)
        
        rule_violations = self.hard_rules.validate(primary_result)
        logger.info(f"Hard rule violations: {len(rule_violations)}")
        
        # Error pattern matching
        pattern_matches = self.error_pattern_db.match(primary_result)
        logger.info(f"Error pattern matches: {len(pattern_matches)}")
        
        # Step 5: Create validation report
        validation_report = ValidationReport(
            document_id=primary_result.document_id,
            validation_status='APPROVED',
            risk_signals=risk_signals.to_dict()
        )
        
        validation_report.add_violations(rule_violations)
        
        # Add pattern matches as warnings
        validation_report.warnings = len(pattern_matches)
        validation_report.pattern_matches = [m.to_dict() for m in pattern_matches]
        
        validation_report.total_checks = self.hard_rules.count_checks(primary_result)
        validation_report.passed_checks = max(
            validation_report.total_checks - validation_report.failed_checks,
            0
        )
        validation_report.calculate_summary()

        confidence = self.confidence_scorer.assess(primary_result, validation_report)
        validation_report.overall_confidence = confidence['score']
        validation_report.confidence_label = confidence['label']
        validation_report.confidence_components = confidence['components']
        validation_report.confidence_notes = confidence['notes']
        validation_report.confidence_metrics = confidence['metrics']
        
        # Step 6: Generate outputs
        logger.info("=" * 80)
        logger.info("Generating Reports")
        logger.info("=" * 80)
        
        csv_path = self.report_gen.generate_csv(primary_result)
        logger.info(f"✓ CSV: {csv_path}")
        
        risk_report_path = self.report_gen.generate_risk_report(validation_report)
        logger.info(f"✓ Risk report: {risk_report_path}")

        validation_report.output_files = {
            'csv': csv_path,
            'risk_report': risk_report_path
        }

        elapsed_seconds = time.monotonic() - start_time
        business_summary_path = self.report_gen.generate_business_summary(
            primary_result,
            validation_report,
            elapsed_seconds
        )
        logger.info(f"✓ Business summary: {business_summary_path}")

        review_rows_path = self.report_gen.generate_review_rows_csv(primary_result, validation_report)
        if review_rows_path:
            logger.info(f"✓ Review rows: {review_rows_path}")

        validation_report.output_files.update({
            'business_summary': business_summary_path,
            'review_rows': review_rows_path
        })
        
        summary = self.report_gen.generate_summary_report(primary_result, validation_report)
        if self.config.emit_summary:
            print("\n" + summary + "\n")
        
        logger.info("Processing complete!")
        
        return primary_result, validation_report
    
    async def process_batch(self, pdf_paths: list) -> list:
        """
        Process multiple PDFs in batch
        
        Returns:
            List of (OCRResult, ValidationReport) tuples
        """
        logger.info(f"Batch processing {len(pdf_paths)} documents")
        
        tasks = [self.process(pdf_path) for pdf_path in pdf_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter successful results
        successful = [r for r in results if not isinstance(r, Exception)]
        failed = [r for r in results if isinstance(r, Exception)]
        
        logger.info(f"Batch complete: {len(successful)} successful, {len(failed)} failed")
        
        return successful
