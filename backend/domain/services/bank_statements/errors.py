"""Domain errors for bank statement parsing."""


class BankStatementParseError(ValueError):
    """Raised when uploaded text is not a valid 1CClientBankExchange statement."""
