"""
Google Document AI Client
Primary OCR engine for bank statement processing
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
from dataclasses import dataclass
from pathlib import Path

from google.cloud import documentai_v1 as documentai
from google.api_core.client_options import ClientOptions
from google.oauth2 import service_account

from ..models.ocr_result import OCRResult, TransactionRow
from ..utils.parsing import parse_amount, parse_date

logger = logging.getLogger(__name__)


@dataclass
class DocumentAIConfig:
    """Configuration for Document AI"""
    project_id: str
    location: str = "us"
    processor_id: Optional[str] = None
    credentials_path: Optional[str] = None

    @property
    def api_endpoint(self) -> str:
        return f"{self.location}-documentai.googleapis.com"


class DocumentAIClient:
    """
    Google Document AI client for bank statement processing
    
    Features:
    - Async document processing
    - Table extraction
    - Confidence scores
    - Optimized for financial documents (Lending Processor)
    """
    
    def __init__(self, config: DocumentAIConfig):
        self.config = config
        if not self.config.project_id or not self.config.processor_id:
            raise ValueError("DocumentAIConfig requires project_id and processor_id")
        
        # Initialize client
        opts = ClientOptions(api_endpoint=self.config.api_endpoint)
        credentials = None
        if self.config.credentials_path:
            credentials_path = Path(self.config.credentials_path).expanduser()
            if not credentials_path.is_file():
                raise FileNotFoundError(f"Document AI credentials not found: {credentials_path}")
            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_path)
            )

        self.client = documentai.DocumentProcessorServiceClient(
            client_options=opts,
            credentials=credentials
        )
        
        # Build processor name
        self.processor_name = self.client.processor_path(
            self.config.project_id,
            self.config.location,
            self.config.processor_id
        )
        
        logger.info(f"Initialized Document AI client: {self.processor_name}")
    
    async def process_document(self, image_content: bytes, 
                              mime_type: str = "application/pdf") -> OCRResult:
        """
        Process a document with Document AI
        
        Args:
            image_content: Binary content of the document
            mime_type: MIME type (application/pdf or image/png, etc.)
        
        Returns:
            OCRResult with extracted data
        """
        logger.info(f"Processing document with Document AI (size: {len(image_content)} bytes)")
        
        # Create request
        raw_document = documentai.RawDocument(
            content=image_content,
            mime_type=mime_type
        )
        
        request = documentai.ProcessRequest(
            name=self.processor_name,
            raw_document=raw_document
        )
        
        # Process document (synchronous API wrapped in async)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, self.client.process_document, request)
        
        document = result.document
        logger.info(f"Document AI processing complete. Pages: {len(document.pages)}")
        
        # Extract and structure data
        ocr_result = self._extract_data(document)
        
        return ocr_result
    
    def _extract_data(self, document: documentai.Document) -> OCRResult:
        """
        Extract structured data from Document AI response
        
        Focus on table extraction for bank statements
        """
        document_id = f"docai_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Extract tables from all pages
        all_rows = []
        row_index = 0
        
        for page_num, page in enumerate(document.pages, 1):
            logger.info(f"Processing page {page_num}/{len(document.pages)}")
            
            # Extract tables from this page
            for table in page.tables:
                table_rows = self._parse_table(table, document.text, page_num, row_index)
                all_rows.extend(table_rows)
                row_index += len(table_rows)
        
        # Detect header
        header = self._detect_header(document.pages[0] if document.pages else None, document.text)
        
        # Create OCR result
        ocr_result = OCRResult(
            document_id=document_id,
            engine="document_ai",
            processed_at=datetime.now().isoformat(),
            rows=all_rows,
            header=header,
            header_detected=bool(header),
            header_confidence=0.9 if header else 0.0,
            page_count=len(document.pages),
            total_rows=len(all_rows),
            overall_confidence=self._extract_page_confidence(document)
        )
        
        # Try to extract opening/closing balance from text
        self._extract_balances(ocr_result, document.text)
        
        logger.info(f"Extracted {len(all_rows)} transaction rows")
        return ocr_result
    
    def _parse_table(self, table: documentai.Document.Page.Table, 
                    full_text: str, page_num: int, start_row_idx: int) -> List[TransactionRow]:
        """
        Parse a single table into transaction rows
        """
        rows = []
        
        # Process body rows (skip header)
        for row_idx, row in enumerate(table.body_rows):
            cells = self._extract_cells(row.cells, full_text)
            
            # Map cells to transaction fields based on position
            # Typical bank statement columns: Date, Description, Withdrawal, Deposit, Balance
            transaction = self._cells_to_transaction(
                cells, 
                page_num, 
                start_row_idx + row_idx
            )
            
            if transaction:
                rows.append(transaction)
        
        return rows
    
    def _extract_cells(self, cells: List[documentai.Document.Page.Table.TableCell], 
                      full_text: str) -> List[Dict[str, Any]]:
        """Extract text and metadata from table cells"""
        extracted_cells = []
        
        for cell in cells:
            cell_text = self._get_text(cell.layout, full_text)
            confidence = cell.layout.confidence if hasattr(cell.layout, 'confidence') else 0.0
            
            extracted_cells.append({
                'text': cell_text.strip(),
                'confidence': confidence,
                'row_span': cell.row_span,
                'col_span': cell.col_span
            })
        
        return extracted_cells
    
    def _cells_to_transaction(self, cells: List[Dict], page_num: int, row_idx: int) -> Optional[TransactionRow]:
        """
        Map table cells to TransactionRow
        
        Assumes column order: Date, Description, Withdrawal, Deposit, Balance
        (Common format for Canadian banks)
        """
        if len(cells) < 3:  # Need at least date, description, amount
            return None
        
        try:
            # Parse based on common formats
            # Column mapping (flexible):
            # - First column: Date
            # - Second column: Description  
            # - Last column: Balance
            # - Middle columns: Withdrawal/Deposit or single Amount
            
            transaction = TransactionRow(
                transaction_date=parse_date(cells[0]['text']),
                description=cells[1]['text'] if len(cells) > 1 else "",
                page_number=page_num,
                row_index=row_idx,
                date_confidence=cells[0]['confidence'],
                description_confidence=cells[1]['confidence'] if len(cells) > 1 else 0.0,
                date_raw=cells[0]['text'],
                amount_raw=cells[-2]['text'] if len(cells) > 3 else ""
            )
            
            # Parse amounts based on column count
            if len(cells) == 5:
                # Format: Date, Description, Withdrawal, Deposit, Balance
                transaction.withdrawal = parse_amount(cells[2]['text'])
                transaction.deposit = parse_amount(cells[3]['text'])
                transaction.balance = parse_amount(cells[4]['text'])
                transaction.amount_confidence = (cells[2]['confidence'] + cells[3]['confidence']) / 2
                transaction.balance_confidence = cells[4]['confidence']
            
            elif len(cells) == 4:
                # Format: Date, Description, Amount, Balance
                amount = parse_amount(cells[2]['text'])
                if amount is not None and amount < 0:
                    transaction.withdrawal = abs(amount)
                elif amount is not None:
                    transaction.deposit = amount
                transaction.balance = parse_amount(cells[3]['text'])
                transaction.amount_confidence = cells[2]['confidence']
                transaction.balance_confidence = cells[3]['confidence']
            
            elif len(cells) == 3:
                # Format: Date, Description, Balance
                transaction.balance = parse_amount(cells[2]['text'])
                transaction.balance_confidence = cells[2]['confidence']
            
            return transaction
            
        except Exception as e:
            logger.warning(f"Failed to parse transaction row {row_idx}: {e}")
            return None
    
    def _detect_header(self, first_page: Optional[documentai.Document.Page], 
                      full_text: str) -> List[str]:
        """
        Detect table header from first page
        """
        if not first_page or not first_page.tables:
            return []
        
        # Get header from first table
        first_table = first_page.tables[0]
        if not first_table.header_rows:
            return []
        
        header = []
        for cell in first_table.header_rows[0].cells:
            header.append(self._get_text(cell.layout, full_text).strip())
        
        return header
    
    def _extract_balances(self, ocr_result: OCRResult, full_text: str):
        """
        Extract opening and closing balance from document text
        """
        # Simple heuristic: look for balance keywords
        import re
        
        # Opening balance
        opening_match = re.search(r'(?:opening|previous|beginning)\s+balance[:\s]+\$?\s*([\d,]+\.?\d{0,2})', 
                                 full_text, re.IGNORECASE)
        if opening_match:
            ocr_result.opening_balance = parse_amount(opening_match.group(1))
        elif ocr_result.rows:
            # Use first row balance as opening
            ocr_result.opening_balance = ocr_result.rows[0].balance
        
        # Closing balance
        closing_match = re.search(r'(?:closing|ending|current)\s+balance[:\s]+\$?\s*([\d,]+\.?\d{0,2})', 
                                 full_text, re.IGNORECASE)
        if closing_match:
            ocr_result.closing_balance = parse_amount(closing_match.group(1))
        elif ocr_result.rows:
            # Use last row balance as closing
            ocr_result.closing_balance = ocr_result.rows[-1].balance
    
    @staticmethod
    def _get_text(layout: documentai.Document.Page.Layout, full_text: str) -> str:
        """Extract text from Layout object"""
        text_segments = []
        for segment in layout.text_anchor.text_segments:
            start_index = int(segment.start_index) if hasattr(segment, 'start_index') else 0
            end_index = int(segment.end_index)
            text_segments.append(full_text[start_index:end_index])
        
        return ''.join(text_segments).strip()
    
    @staticmethod
    def _extract_page_confidence(document: documentai.Document) -> float:
        """Extract a best-effort overall confidence score."""
        if not document.pages:
            return 0.0

        page_quality = document.pages[0].page_quality
        if page_quality and page_quality.quality_score is not None:
            return float(page_quality.quality_score)
        return 0.0
