# Fix Route 53 Registered Domain Nameservers

## The Problem
Your hosted zone has the correct nameservers, but the domain registration is using different nameservers.

## Current Status

### Hosted Zone (CORRECT)
- Location: Route 53 > Hosted zones > eshkol.ai
- Nameservers:
  - ns-1673.awsdns-17.co.uk
  - ns-286.awsdns-35.com
  - ns-690.awsdns-22.net
  - ns-1252.awsdns-28.org
- Status: ✓ Configured correctly

### Domain Registration (WRONG)
- The domain registration is using: dns1.registrar-servers.com
- This needs to be updated to match the hosted zone nameservers

## Solution: Update Domain Registration Nameservers

### Option 1: AWS Console (Recommended)

1. Go to AWS Console: https://console.aws.amazon.com/route53/
2. Click "Registered domains" in the left menu
3. Find and click on "eshkol.ai"
4. Click "Add or edit name servers"
5. Replace the current nameservers with these 4:
   ```
   ns-1673.awsdns-17.co.uk
   ns-286.awsdns-35.com
   ns-690.awsdns-22.net
   ns-1252.awsdns-28.org
   ```
6. Click "Update"
7. Wait 1-2 hours for DNS propagation

### Option 2: AWS CLI

Run this command:
```powershell
aws route53domains update-domain-nameservers `
  --region us-east-1 `
  --domain-name eshkol.ai `
  --nameservers Name=ns-1673.awsdns-17.co.uk Name=ns-286.awsdns-35.com Name=ns-690.awsdns-22.net Name=ns-1252.awsdns-28.org
```

## If Domain is NOT in "Registered Domains"

If you don't see eshkol.ai in Route 53 > Registered domains, then:

1. **Check if you're in the correct AWS account**
   - Current account: 991105135552
   - Maybe the domain was registered in a different account?

2. **Check if domain was registered elsewhere**
   - Namecheap
   - GoDaddy
   - Google Domains
   - Cloudflare
   - etc.

3. **If registered elsewhere:**
   - Log in to that registrar
   - Update nameservers to the Route 53 nameservers listed above

## Verify After Update

After updating, wait 1-2 hours and run:
```powershell
nslookup -type=NS eshkol.ai 8.8.8.8
```

Should show:
```
eshkol.ai       nameserver = ns-1673.awsdns-17.co.uk
eshkol.ai       nameserver = ns-286.awsdns-35.com
eshkol.ai       nameserver = ns-690.awsdns-22.net
eshkol.ai       nameserver = ns-1252.awsdns-28.org
```

Then test:
```powershell
nslookup www.eshkol.ai 8.8.8.8
```

Should resolve to:
```
www.eshkol.ai   canonical name = www.eshkol.ai.s3-website-us-east-1.amazonaws.com
```

## Important Notes

- Hosted zone nameservers and domain registration nameservers MUST match
- The hosted zone is just DNS hosting - it doesn't control the domain registration
- The domain registration controls what the internet sees
- Both must point to the same nameservers for DNS to work
