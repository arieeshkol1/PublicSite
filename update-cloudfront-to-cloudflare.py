#!/usr/bin/env python3
"""
Script to replace CloudFront references with Cloudflare in documentation files
"""

import os
import re

# Files to update
files_to_update = [
    'ACCESS-PATTERNS-DIAGRAM-GUIDE.md',
    'CONNECTIVITY-CASES-DIAGRAM-GUIDE.md',
    'ACCESS-PATTERNS-COMPLETE-SUMMARY.md'
]

# Replacement mappings
replacements = {
    'CloudFront': 'Cloudflare',
    'Amazon CloudFront': 'Cloudflare Proxy',
    'AWS CloudFront': 'Cloudflare',
    'CloudFront CDN': 'Cloudflare Proxy',
    'CloudFront (CDN)': 'Cloudflare (CDN)',
    'CloudFront edge': 'Cloudflare edge',
    'WAF at the CloudFront edge': 'Cloudflare WAF at the edge',
    'WAF at CloudFront edge': 'Cloudflare WAF',
    'AWS Shield': 'Cloudflare DDoS Protection',
    'CloudFront →': 'Cloudflare →',
    '→ CloudFront': '→ Cloudflare',
    '[Amazon CloudFront]': '[Cloudflare Proxy]',
    '[CloudFront]': '[Cloudflare]',
    'Add CloudFront': 'Add Cloudflare',
    'CloudFront icon': 'Cloudflare icon',
    'CloudFront below': 'Cloudflare below',
    'through CloudFront': 'through Cloudflare',
    'use CloudFront': 'use Cloudflare',
    'CloudFront with': 'Cloudflare with',
    'CloudFront as': 'Cloudflare as',
    'CloudFront provides': 'Cloudflare provides',
    'CloudFront reduces': 'Cloudflare reduces',
    'CloudFront caching': 'Cloudflare caching'
}

def update_file(filepath):
    """Update a single file with CloudFront → Cloudflare replacements"""
    if not os.path.exists(filepath):
        print(f"⚠️  File not found: {filepath}")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    changes_made = 0
    
    # Apply replacements
    for old_text, new_text in replacements.items():
        if old_text in content:
            count = content.count(old_text)
            content = content.replace(old_text, new_text)
            changes_made += count
            print(f"  ✓ Replaced '{old_text}' → '{new_text}' ({count} times)")
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Updated {filepath} ({changes_made} replacements)")
        return True
    else:
        print(f"ℹ️  No changes needed in {filepath}")
        return False

def main():
    print("=" * 60)
    print("CloudFront → Cloudflare Documentation Update")
    print("=" * 60)
    print()
    
    updated_files = []
    skipped_files = []
    
    for filepath in files_to_update:
        print(f"\nProcessing: {filepath}")
        print("-" * 60)
        if update_file(filepath):
            updated_files.append(filepath)
        else:
            skipped_files.append(filepath)
    
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"✅ Updated: {len(updated_files)} files")
    print(f"ℹ️  Skipped: {len(skipped_files)} files")
    print()
    
    if updated_files:
        print("Updated files:")
        for f in updated_files:
            print(f"  • {f}")
    
    if skipped_files:
        print("\nSkipped files (no changes needed):")
        for f in skipped_files:
            print(f"  • {f}")

if __name__ == '__main__':
    main()
