# Contributing to Q-Guardian

Thank you for your interest in contributing to Q-Guardian. This document provides guidelines for contributing to the project.

> **Note:** Q-Guardian is currently in a private research phase. This document is prepared for when the repository becomes public.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/ssahilkhan/q-guardian.git
cd q-guardian

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Install with dev dependencies
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=q_guardian --cov-report=html
```

## Code Quality

```bash
# Linting
ruff check src/ tests/

# Formatting
ruff format src/ tests/

# Type checking
mypy src/q_guardian/
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Guidelines

- Write tests for new functionality
- Maintain type hint coverage
- Follow existing code style
- Update documentation for significant changes
- Keep commits focused and well-described

## Reporting Issues

Use the GitHub issue templates for bug reports, feature requests, and questions.
