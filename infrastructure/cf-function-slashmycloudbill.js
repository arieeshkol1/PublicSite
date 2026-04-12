// CloudFront Function for slashmycloudbill.com
// Files are at the ROOT of the slashmycloudbill.com bucket:
//   /index.html          → landing page
//   /members/index.html  → member portal
//   /admin/index.html    → admin panel
//
// This function handles SPA routing (return index.html for unknown paths)
// and ensures www redirects to root domain.

function handler(event) {
    var request = event.request;
    var host = (request.headers.host && request.headers.host.value) || '';
    var uri = request.uri;

    // Redirect www to root domain
    if (host.startsWith('www.')) {
        return {
            statusCode: 301,
            statusDescription: 'Moved Permanently',
            headers: {
                location: { value: 'https://slashmycloudbill.com' + uri }
            }
        };
    }

    // If requesting a file with extension, serve as-is
    var ext = uri.split('.').pop().toLowerCase();
    var staticExts = ['css','js','png','jpg','jpeg','gif','svg','ico','woff','woff2','ttf','map','json','pdf','html'];
    if (staticExts.indexOf(ext) !== -1) {
        return request;
    }

    // Directory paths — ensure they end with /index.html
    if (uri === '/' || uri === '') {
        request.uri = '/index.html';
        return request;
    }

    if (uri.endsWith('/')) {
        request.uri = uri + 'index.html';
        return request;
    }

    // For paths without extension (SPA routes), serve the section's index.html
    if (uri.startsWith('/members')) {
        request.uri = '/members/index.html';
        return request;
    }

    if (uri.startsWith('/admin')) {
        request.uri = '/admin/index.html';
        return request;
    }

    // Default: serve root index.html
    request.uri = '/index.html';
    return request;
}
