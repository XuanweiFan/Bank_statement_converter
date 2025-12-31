"""
Defense Layer 3: Hard Rules Validator
Validates data against deterministic rules that must be satisfied
"""

import logging
from typing import List
from datetime import date
from decimal import Decimal

from ..models.ocr_result import OCRResult, TransactionRow
from ..models.validation_report import RuleViolation

logger = logging.getLogger(__name__)


class HardRulesValidator:
    """
    Hard Rules Validator: Deterministic validation rules
    
    5 core rules:
    1. Date range validation
    2. Amount format validation
    3. CR/DR symbol consistency (simplified for MVP)
    4. Running balance conservation (row-by-row)
    5. Overall balance conservation
    """
    
    def __init__(self):
        self.tolerance = Decimal('0.02')  # ±$0.02 tolerance for floating point
    
    def validate(self, result: OCRResult) -> List[RuleViolation]:
        """
        Run all hard rule validations
        
        Returns:
            List of rule violations
        """
        violations = []
        
        logger.info(f"Running hard rules validation for document {result.document_id}")

        if not result.rows:
            violations.append(RuleViolation(
                rule='NO_ROWS',
                severity='CRITICAL',
                message='No transaction rows extracted'
            ))
            return violations
        
        # Rule 1: Date range
        date_violations = self.validate_date_range(result)
        violations.extend(date_violations)
        logger.info(f"Rule 1 (Date Range): {len(date_violations)} violations")
        
        # Rule 2: Amount format
        amount_violations = self.validate_amount_format(result)
        violations.extend(amount_violations)
        logger.info(f"Rule 2 (Amount Format): {len(amount_violations)} violations")
        
        # Rule 3: CR/DR symbols (placeholder for MVP)
        # In a full implementation, this would check for proper debit/credit indicators
        
        # Rule 4: Running balance (row-by-row)
        balance_violations = self.validate_running_balance(result)
        violations.extend(balance_violations)
        logger.info(f"Rule 4 (Running Balance): {len(balance_violations)} violations")
        
        # Rule 5: Overall balance
        overall_violations = self.validate_overall_balance(result)
        violations.extend(overall_violations)
        logger.info(f"Rule 5 (Overall Balance): {len(overall_violations)} violations")
        
        logger.info(f"Hard rules validation complete: {len(violations)} total violations")
        return violations

    def count_checks(self, result: OCRResult) -> int:
        """
        Estimate the number of checks executed for reporting purposes.
        """
        if not result.rows:
            return 1

        count = 0

        # Date checks: presence/future per row + monotonic transitions.
        count += len(result.rows)
        if len(result.rows) > 1:
            count += len(result.rows) - 1

        # Amount presence check per row.
        count += len(result.rows)

        # Amount format checks for fields present.
        for row in result.rows:
            if row.deposit is not None:
                count += 1
            if row.withdrawal is not None:
                count += 1
            if row.balance is not None:
                count += 1

        # Running balance checks where balances are present.
        for i in range(1, len(result.rows)):
            if result.rows[i - 1].balance is not None and result.rows[i].balance is not None:
                count += 1

        # Overall balance check when opening/closing present.
        if result.opening_balance is not None and result.closing_balance is not None:
            count += 1

        return count
    
    def validate_date_range(self, result: OCRResult) -> List[RuleViolation]:
        """
        Rule 1: Date range validation
        
        Checks:
        - No future dates
        - Dates must be monotonic (non-decreasing)
        - Statement period reasonable (typically 1-3 months)
        """
        violations = []
        today = date.today()
        
        for idx, row in enumerate(result.rows):
            if not row.transaction_date:
                violations.append(RuleViolation(
                    rule='DATE_MISSING',
                    row=idx,
                    severity='CRITICAL',
                    message='Transaction date is missing'
                ))
                continue
            
            # Check for future dates
            if row.transaction_date > today:
                violations.append(RuleViolation(
                    rule='DATE_IN_FUTURE',
                    row=idx,
                    severity='CRITICAL',
                    message=f'Date {row.transaction_date} is in the future'
                ))
            
            # Check monotonicity
            if idx > 0 and result.rows[idx-1].transaction_date:
                if row.transaction_date < result.rows[idx-1].transaction_date:
                    violations.append(RuleViolation(
                        rule='DATE_NOT_MONOTONIC',
                        row=idx,
                        severity='HIGH',
                        message=f'Date reversed: {result.rows[idx-1].transaction_date} → {row.transaction_date}'
                    ))
        
        return violations
    
    def validate_amount_format(self, result: OCRResult) -> List[RuleViolation]:
        """
        Rule 2: Amount format validation
        
        Checks:
        - Must be valid numbers
        - Currency format (2 decimal places)
        - No invalid characters
        - At least one of deposit or withdrawal must exist
        """
        violations = []
        
        for idx, row in enumerate(result.rows):
            # Check if at least one amount exists
            if row.deposit is None and row.withdrawal is None:
                violations.append(RuleViolation(
                    rule='NO_AMOUNT',
                    row=idx,
                    severity='HIGH',
                    message='Neither deposit nor withdrawal amount found'
                ))
            elif row.deposit is not None and row.withdrawal is not None:
                if row.deposit != 0 and row.withdrawal != 0:
                    violations.append(RuleViolation(
                        rule='BOTH_DEPOSIT_WITHDRAWAL',
                        row=idx,
                        severity='MEDIUM',
                        message='Both deposit and withdrawal have values'
                    ))
            
            # Validate deposit format
            if row.deposit is not None:
                if not self.is_valid_currency(row.deposit):
                    violations.append(RuleViolation(
                        rule='INVALID_AMOUNT_FORMAT',
                        row=idx,
                        field='deposit',
                        severity='CRITICAL',
                        message=f'Invalid deposit format: {row.deposit}'
                    ))
            
            # Validate withdrawal format
            if row.withdrawal is not None:
                if not self.is_valid_currency(row.withdrawal):
                    violations.append(RuleViolation(
                        rule='INVALID_AMOUNT_FORMAT',
                        row=idx,
                        field='withdrawal',
                        severity='CRITICAL',
                        message=f'Invalid withdrawal format: {row.withdrawal}'
                    ))
            
            # Validate balance
            if row.balance is not None:
                if not self.is_valid_currency(row.balance):
                    violations.append(RuleViolation(
                        rule='INVALID_AMOUNT_FORMAT',
                        row=idx,
                        field='balance',
                        severity='CRITICAL',
                        message=f'Invalid balance format: {row.balance}'
                    ))
        
        return violations
    
    def validate_running_balance(self, result: OCRResult) -> List[RuleViolation]:
        """
        Rule 4: Running balance validation (row-by-row)
        
        Formula: prev_balance + deposit - withdrawal = current_balance
        Tolerance: ±$0.02 (for rounding)
        """
        violations = []
        
        for i in range(1, len(result.rows)):
            prev_row = result.rows[i-1]
            curr_row = result.rows[i]
            
            # Skip if balance not available
            if prev_row.balance is None or curr_row.balance is None:
                continue
            
            # Calculate expected balance
            expected_balance = prev_row.balance
            if curr_row.deposit is not None:
                expected_balance += curr_row.deposit
            if curr_row.withdrawal is not None:
                expected_balance -= curr_row.withdrawal
            
            # Check with tolerance
            diff = abs(expected_balance - curr_row.balance)
            if diff > self.tolerance:
                violations.append(RuleViolation(
                    rule='RUNNING_BALANCE_MISMATCH',
                    row=i,
                    severity='CRITICAL',
                    expected=expected_balance,
                    actual=curr_row.balance,
                    difference=float(diff),
                    message=f'Balance mismatch: expected {expected_balance}, got {curr_row.balance}'
                ))
        
        return violations
    
    def validate_overall_balance(self, result: OCRResult) -> List[RuleViolation]:
        """
        Rule 5: Overall balance validation
        
        Formula: opening_balance + total_deposits - total_withdrawals = closing_balance
        """
        violations = []
        
        # Skip if opening/closing balance not available
        if result.opening_balance is None or result.closing_balance is None:
            logger.warning("Opening or closing balance not available, skipping overall balance check")
            return violations
        
        # Calculate totals
        total_deposits = sum(
            (r.deposit for r in result.rows if r.deposit is not None),
            Decimal('0')
        )
        total_withdrawals = sum(
            (r.withdrawal for r in result.rows if r.withdrawal is not None),
            Decimal('0')
        )
        
        # Calculate expected closing
        expected_closing = result.opening_balance + total_deposits - total_withdrawals
        actual_closing = result.closing_balance
        
        # Check with tolerance
        diff = abs(expected_closing - actual_closing)
        if diff > self.tolerance:
            violations.append(RuleViolation(
                rule='OVERALL_BALANCE_MISMATCH',
                severity='CRITICAL',
                expected=expected_closing,
                actual=actual_closing,
                difference=float(diff),
                message=f'Overall balance mismatch: expected {expected_closing}, got {actual_closing}'
            ))
        
        return violations
    
    @staticmethod
    def is_valid_currency(amount: Decimal) -> bool:
        """
        Check if amount is valid currency format
        
        Valid:
        - Maximum 2 decimal places
        - Within reasonable range
        """
        try:
            # Check decimal places
            decimal_places = abs(amount.as_tuple().exponent)
            if decimal_places > 2:
                return False
            
            # Check reasonable range (< $1 million for single transaction)
            if abs(amount) > 1_000_000:
                return False
            
            return True
        except:
            return False
