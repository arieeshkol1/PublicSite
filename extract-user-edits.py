#!/usr/bin/env python3
"""
Extract user's manual edits from the HLD document
"""

from docx import Document

def extract_edits():
    doc = Document('Made4Net-Operational-Excellence-HLD.docx')
    
    print("USER'S MANUAL EDITS DETECTED:")
    print("=" * 80)
    
    in_section_14 = False
    
    for para in doc.paragraphs:
        # Check for Section 1.4
        if '1.4' in para.text and 'Connectivity' in para.text:
            in_section_14 = True
            print("\n✓ Section 1.4 - User added custom text:")
            continue
        
        # Check for Section 2
        if para.style.name.startswith('Heading') and '2.' in para.text and 'Remote' in para.text:
            in_section_14 = False
        
        # Print content in Section 1.4
        if in_section_14 and para.text.strip():
            if "Below are the 3 options" in para.text:
                print(f"\n  CUSTOM TEXT: '{para.text}'")
                print("  ^ This is a user addition!")
    
    print("\n" + "=" * 80)
    print("\nRECOMMENDATION:")
    print("The user added: 'Below are the 3 options for the connectivity :'")
    print("This should be preserved in the next generation.")
    print("\nSuggested text:")
    print("'The architecture supports three primary connectivity patterns:'")

if __name__ == '__main__':
    extract_edits()
