import os
import sys

# Add the src directory to the Python path
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
sys.path.insert(0, src_path)

# Import and run the main function
from src.main import main

if __name__ == '__main__':
    sys.exit(main())

