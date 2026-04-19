# Contributing to AetherOS

## Development Setup

```bash
git clone https://github.com/DAXXTEAM/AetherOS-New-Update.git
cd AetherOS-New-Update
pip install -r requirements.txt
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Code Style
- Follow PEP 8 conventions
- Use type annotations for all public functions
- Add docstrings for classes and public methods
- Keep modules under 500 lines when possible

## Module Structure
Each new module should include:
1. `__init__.py` with exports
2. Implementation files
3. Corresponding test file in `tests/`
4. Documentation updates

## Author
Arpit-DAXX <admin@daxxteam.io>
