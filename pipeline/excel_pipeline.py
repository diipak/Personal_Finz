import sys
import os

# allow imports from project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.excel_parser import parse_excel

input_file = sys.argv[1]
output_file = sys.argv[2]

df = parse_excel(input_file)

df.to_csv(output_file,index=False)