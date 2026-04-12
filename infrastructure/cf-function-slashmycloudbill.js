// CloudFront Function: slashmycloudbill.com URL routing
// Attached to the viewer-request event on the existing CloudFront distribution.
//
// Rules:
//   slashmycloudbill.com/           → /slashMyBill/index.html
//   slashmycloudbill.com/members/*  → /members/* (unchanged)
//   slashmycloudbill.com/admin/*    → /admin/* (unchanged)
//   slashmycloudbill.com/*          → /slashMyBill/* (prefix all other paths)
//   eshkolai.com/*                  → unchanged (existing behavior)

function handler(event) {
    var request = event.request;
    var host = (request.headers.host && request.headers.host.value) || '';
    var uri = request.uri;

    // Only rewrite for slashmycloudbill.com
    if (host.indexOf('slashmycloudbill.com') === -1) {
        return request;
    }

    // Root → SlashMyBill landing page
    if (uri === '/' || uri === '') {
        request.uri = '/slashMyBill/index.html';
        return request;
    }

    // /members/* → keep as-is (member portal)
    if (uri.startsWith('/members/') || uri === '/members') {
        return request;
    }

    // /admin/* → keep as-is
    if (uri.startsWith('/admin/') || uri === '/admin') {
        return request;
    }

    // /slashMyBill/* → keep as-is (already correct)
    if (uri.startsWith('/slashMyBill/')) {
        return request;
    }

    // Static assets at root level (styles, images, etc.) → keep as-is
    var ext = uri.split('.').pop().toLowerCase();
    var staticExts = ['css', 'js', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'ico', 'woff', 'woff2', 'ttf'];
    if (staticExts.indexOf(ext) !== -1) {
        return request;
    }

    // Everything else → prefix with /slashMyBill/
    request.uri = '/slashMyBill' + uri;
    return request;
}
