content = open('member-handler/lambda_function.py', 'r', encoding='utf-8').read()

old = """        'findings': all_findings,
        'totalSavings': round(total_savings, 2),
        'scannedAccounts': len(account_ids),
        'scannedAt': datetime.now(timezone.utc).isoformat(),
    })"""

scanned_at = "datetime.now(timezone.utc).isoformat()"
new = """        'findings': all_findings,
        'totalSavings': round(total_savings, 2),
        'scannedAccounts': len(account_ids),
        'scannedAt': datetime.now(timezone.utc).isoformat(),
    })

    # Cache scan result for the Chat widget (last-scan endpoint)
    _save_last_scan(member_email, account_ids, all_findings, round(total_savings, 2))

    return result"""

# We need to capture the result before returning
old2 = """    all_cards.sort(key=lambda c: (c.get('monthlySavings') or 0), reverse=True)
    all_findings.sort(key=lambda f: (f.get('savingsUsd') or 0), reverse=True)

    return create_response(200, {
        'cards': all_cards,
        'findings': all_findings,
        'totalSavings': round(total_savings, 2),
        'scannedAccounts': len(account_ids),
        'scannedAt': datetime.now(timezone.utc).isoformat(),
    })"""

new2 = """    all_cards.sort(key=lambda c: (c.get('monthlySavings') or 0), reverse=True)
    all_findings.sort(key=lambda f: (f.get('savingsUsd') or 0), reverse=True)

    scanned_at = datetime.now(timezone.utc).isoformat()
    result = create_response(200, {
        'cards': all_cards,
        'findings': all_findings,
        'totalSavings': round(total_savings, 2),
        'scannedAccounts': len(account_ids),
        'scannedAt': scanned_at,
    })

    # Cache top findings for the Chat widget
    _save_last_scan(member_email, account_ids, all_findings[:10], round(total_savings, 2), scanned_at)

    return result"""

if old2 in content:
    content = content.replace(old2, new2)
    print('Return patched OK')
else:
    print('ERROR: return pattern not found')
    idx = content.find('all_cards.sort')
    print(repr(content[idx:idx+400]))

open('member-handler/lambda_function.py', 'w', encoding='utf-8').write(content)
