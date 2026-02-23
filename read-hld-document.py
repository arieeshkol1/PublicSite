#!/usr/bin/env python3
"""
Read the existing HLD document to understand user's manual edits
"""

from docx import Document

def read_hld_document():
    try:
        doc = Document('Made4Net-Operational-Excellence-HLD.docx')
        
        print("=" * 80)
        print("READING EXISTING HLD DOCUMENT")
        print("=" * 80)
        print()
        
        section_count = 0
        
        for para in doc.paragraphs:
            # Check if it's a heading
            if para.style.name.startswith('Heading'):
                section_count += 1
                level = para.style.name.replace('Heading ', '')
                indent = "  " * (int(level) - 1) if level.isdigit() else ""
                print(f"\n{indent}{'#' * (int(level) if level.isdigit() else 1)} {para.text}")
            # Print first 100 chars of regular paragraphs
            elif para.text.strip():
                text = para.text.strip()
                if len(text) > 100:
                    print(f"  {text[:100]}...")
                else:
                    print(f"  {text}")
        
        print()
        print("=" * 80)
        print(f"Total sections found: {section_count}")
        print("=" * 80)
        
    except Exception as e:
        print(f"Error reading document: {e}")
        print("\nPlease ensure:")
        print("1. The file 'Made4Net-Operational-Excellence-HLD.docx' exists")
        print("2. The file is not open in Word")
        print("3. You have read permissions")

if __name__ == '__main__':
    read_hld_document()
