"""Portable paths for the final product workflow; datasets remain local."""
import os
from pathlib import Path
PACKAGE = Path(__file__).resolve().parents[2]
CODE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('A500_PRODUCT_DATA', PACKAGE / 'Data/product')).expanduser().resolve()
RAW = DATA / 'raw'
RESULT = Path(os.environ.get('A500_PRODUCT_OUTPUT', PACKAGE / 'Result/reproduced')).expanduser().resolve()
REFERENCE = PACKAGE / 'Result/reference'
MODELS = {'linear': ('final', 'external'), 'tree': ('final_tree', 'tree'), 'fusion': ('final_fusion', 'fusion')}
