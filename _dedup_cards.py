content = open('member-handler/lambda_function.py', 'r', encoding='utf-8').read()

old = """    all_cards.sort(key=lambda c: (c.get('monthlySavings') or 0), reverse=True)
    all_findings.sort(key=lambda f: (f.get('savingsUsd') or 0), reverse=True)"""

new = """    # Deduplicate cards: merge multiple cards of the same type+account into one
    # (happens when multiple tips map to the same check function, e.g. s3-002 and s3-003)
    seen_card_ids = {}
    deduped_cards = []
    for card in all_cards:
        cid = card.get('cardId', '')
        if cid not in seen_card_ids:
            seen_card_ids[cid] = card
            deduped_cards.append(card)
        else:
            # Merge resources from duplicate into existing card
            existing = seen_card_ids[cid]
            existing_res = existing.get('resources') or []
            new_res = card.get('resources') or []
            # Add resources not already present (by id/name)
            existing_ids = {r.get('id') or r.get('name') for r in existing_res}
            for r in new_res:
                rid = r.get('id') or r.get('name')
                if rid not in existing_ids:
                    existing_res.append(r)
                    existing_ids.add(rid)
            existing['resources'] = existing_res
            existing['count'] = len(existing_res)
    all_cards = deduped_cards

    all_cards.sort(key=lambda c: (c.get('monthlySavings') or 0), reverse=True)
    all_findings.sort(key=lambda f: (f.get('savingsUsd') or 0), reverse=True)"""

if old in content:
    content = content.replace(old, new)
    print('Dedup logic added OK')
else:
    print('ERROR: pattern not found')

open('member-handler/lambda_function.py', 'w', encoding='utf-8').write(content)
