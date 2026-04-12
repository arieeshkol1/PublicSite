/* Slash My Bill - Client-side logic for AWS bill analysis */

const API_GATEWAY_URL = 'https://l2fd4h481h.execute-api.us-east-1.amazonaws.com';

const MAX_FILE_SIZE = 10485760; // 10 MB
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_REGEX = /^[\d\s\+\-\(\)\.]{7,20}$/;

// OTP States
const OTP_STATE = { UNVERIFIED: 'UNVERIFIED', SENDING: 'SENDING', CODE_SENT: 'CODE_SENT', VERIFYING: 'VERIFYING', VERIFIED: 'VERIFIED' };

document.addEventListener('DOMContentLoaded', () => {
  // DOM references
  const form = document.getElementById('vmb-form');
  const nameInput = document.getElementById('vmb-name');
  const nameError = document.getElementById('vmb-name-error');
  const companyInput = document.getElementById('vmb-company');
  const companyError = document.getElementById('vmb-company-error');
  const emailInput = document.getElementById('vmb-email');
  const emailError = document.getElementById('vmb-email-error');
  const phoneInput = document.getElementById('vmb-phone');
  const phoneError = document.getElementById('vmb-phone-error');
  const fileInput = document.getElementById('vmb-file');
  const fileError = document.getElementById('vmb-file-error');
  const filenameDisplay = document.getElementById('vmb-filename');
  const submitBtn = document.getElementById('vmb-submit');
  const loadingSection = document.getElementById('vmb-loading');
  const resultsSection = document.getElementById('vmb-results');
  const summaryText = document.getElementById('vmb-summary');
  const downloadLink = document.getElementById('vmb-download');
  const errorSection = document.getElementById('vmb-error');
  const errorMessage = document.getElementById('vmb-error-message');
  const retryBtn = document.getElementById('vmb-retry');

  // OTP DOM references
  const verifyBtn = document.getElementById('vmb-verify-email');
  const verifyStatus = document.getElementById('vmb-verify-status');
  const otpSection = document.getElementById('vmb-otp-section');
  const otpInput = document.getElementById('vmb-otp-input');
  const otpSubmitBtn = document.getElementById('vmb-otp-submit');
  const otpError = document.getElementById('vmb-otp-error');
  const resendLink = document.getElementById('vmb-resend-otp');
  const cooldownSpan = document.getElementById('vmb-cooldown');
  const filePickerWrapper = document.getElementById('vmb-file-picker-wrapper');
  const fileOverlay = document.getElementById('vmb-file-overlay');

  // Validation state
  let nameValid = false;
  let companyValid = false;
  let emailValid = false;
  let phoneValid = false;
  let fileValid = false;

  // OTP state
  let otpState = OTP_STATE.UNVERIFIED;
  let verifiedEmail = null;
  let cooldownTimer = null;
  let cooldownRemaining = 0;

  function updateSubmitState() {
    submitBtn.disabled = !(nameValid && companyValid && emailValid && phoneValid && fileValid && otpState === OTP_STATE.VERIFIED);
  }

  function validateName() {
    const value = nameInput.value.trim();
    if (!value) { nameValid = false; nameError.textContent = ''; }
    else if (value.length < 2) { nameValid = false; nameError.textContent = 'Name must be at least 2 characters'; }
    else { nameValid = true; nameError.textContent = ''; }
    updateSubmitState();
    updateVerifyButton();
  }

  function validateCompany() {
    const value = companyInput.value.trim();
    if (!value) { companyValid = false; companyError.textContent = ''; }
    else if (value.length < 2) { companyValid = false; companyError.textContent = 'Company name must be at least 2 characters'; }
    else { companyValid = true; companyError.textContent = ''; }
    updateSubmitState();
  }

  function validateEmail() {
    const value = emailInput.value.trim();
    if (!value) { emailValid = false; emailError.textContent = ''; }
    else if (!EMAIL_REGEX.test(value)) { emailValid = false; emailError.textContent = 'Please enter a valid email address'; }
    else { emailValid = true; emailError.textContent = ''; }

    // Reset verification if email changed after verification
    if (verifiedEmail && value.toLowerCase() !== verifiedEmail) {
      resetOTPState();
    }

    updateSubmitState();
    updateVerifyButton();
  }

  function validatePhone() {
    const value = phoneInput.value.trim();
    if (!value) { phoneValid = false; phoneError.textContent = ''; }
    else if (!PHONE_REGEX.test(value)) { phoneValid = false; phoneError.textContent = 'Please enter a valid phone number'; }
    else { phoneValid = true; phoneError.textContent = ''; }
    updateSubmitState();
    updateVerifyButton();
  }

  function validateFile() {
    const file = fileInput.files[0];
    fileError.textContent = '';
    filenameDisplay.textContent = '';
    if (!file) { fileValid = false; updateSubmitState(); return; }
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (ext !== '.pdf') { fileValid = false; fileError.textContent = 'Only PDF files are supported'; fileInput.value = ''; updateSubmitState(); return; }
    if (file.size === 0) { fileValid = false; fileError.textContent = 'The selected file is empty'; fileInput.value = ''; updateSubmitState(); return; }
    if (file.size > MAX_FILE_SIZE) { fileValid = false; fileError.textContent = 'File exceeds 10 MB limit'; fileInput.value = ''; updateSubmitState(); return; }
    fileValid = true;
    filenameDisplay.textContent = file.name;
    updateSubmitState();
  }

  // ============================================================
  // OTP Logic
  // ============================================================

  function updateVerifyButton() {
    if (otpState === OTP_STATE.VERIFIED) {
      verifyBtn.hidden = true;
      return;
    }
    verifyBtn.hidden = false;
    const canVerify = nameValid && emailValid && phoneValid && otpState === OTP_STATE.UNVERIFIED && cooldownRemaining <= 0;
    verifyBtn.disabled = !canVerify;
  }

  function setOTPState(newState) {
    otpState = newState;
    updateVerifyButton();
    updateSubmitState();
    updateFilePickerState();

    // UI updates per state
    switch (newState) {
      case OTP_STATE.UNVERIFIED:
        otpSection.hidden = true;
        verifyBtn.hidden = false;
        verifyBtn.querySelector('span').textContent = 'Verify my email';
        verifyBtn.classList.remove('vmb-loading-btn');
        setVerifyStatus('', '');
        break;
      case OTP_STATE.SENDING:
        verifyBtn.disabled = true;
        verifyBtn.querySelector('span').textContent = 'Sending...';
        verifyBtn.classList.add('vmb-loading-btn');
        otpError.textContent = '';
        break;
      case OTP_STATE.CODE_SENT:
        verifyBtn.hidden = true;
        verifyBtn.classList.remove('vmb-loading-btn');
        otpSection.hidden = false;
        otpInput.value = '';
        otpInput.focus();
        break;
      case OTP_STATE.VERIFYING:
        otpSubmitBtn.disabled = true;
        otpSubmitBtn.textContent = 'Verifying...';
        break;
      case OTP_STATE.VERIFIED:
        verifiedEmail = emailInput.value.trim().toLowerCase();
        otpSection.hidden = true;
        verifyBtn.hidden = true;
        setVerifyStatus('✓ Email verified', 'success');
        break;
    }
  }

  function updateFilePickerState() {
    const verified = otpState === OTP_STATE.VERIFIED;
    if (verified) {
      filePickerWrapper.classList.remove('vmb-file-picker-disabled');
      filePickerWrapper.classList.add('vmb-file-picker-enabled');
      fileOverlay.hidden = true;
      fileInput.disabled = false;
    } else {
      filePickerWrapper.classList.add('vmb-file-picker-disabled');
      filePickerWrapper.classList.remove('vmb-file-picker-enabled');
      fileOverlay.hidden = false;
      fileInput.disabled = true;
      fileInput.value = '';
      fileValid = false;
      filenameDisplay.textContent = '';
    }
  }

  function setVerifyStatus(msg, type) {
    verifyStatus.textContent = msg;
    verifyStatus.className = 'vmb-verify-status';
    if (type === 'success') verifyStatus.classList.add('vmb-status-success');
    else if (type === 'error') verifyStatus.classList.add('vmb-status-error');
  }

  function resetOTPState() {
    verifiedEmail = null;
    clearCooldown();
    setOTPState(OTP_STATE.UNVERIFIED);
  }

  function startCooldown(seconds) {
    clearCooldown();
    cooldownRemaining = seconds;
    updateCooldownDisplay();
    cooldownTimer = setInterval(() => {
      cooldownRemaining--;
      if (cooldownRemaining <= 0) {
        clearCooldown();
        updateVerifyButton();
        return;
      }
      updateCooldownDisplay();
    }, 1000);
    // Disable verify/resend during cooldown
    verifyBtn.disabled = true;
    resendLink.classList.add('vmb-resend-disabled');
  }

  function clearCooldown() {
    if (cooldownTimer) { clearInterval(cooldownTimer); cooldownTimer = null; }
    cooldownRemaining = 0;
    cooldownSpan.textContent = '';
    resendLink.classList.remove('vmb-resend-disabled');
  }

  function updateCooldownDisplay() {
    cooldownSpan.textContent = `(${cooldownRemaining}s)`;
  }

  async function sendOTP() {
    const email = emailInput.value.trim().toLowerCase();
    setOTPState(OTP_STATE.SENDING);
    try {
      const res = await fetch(`${API_GATEWAY_URL}/send-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      const data = await res.json();
      if (!res.ok) {
        if (res.status === 429 && data.retryAfter) {
          startCooldown(data.retryAfter);
          setOTPState(OTP_STATE.UNVERIFIED);
          setVerifyStatus(data.message || 'Please wait before requesting a new code', 'error');
        } else {
          setOTPState(OTP_STATE.UNVERIFIED);
          setVerifyStatus(data.message || 'Failed to send code. Please try again.', 'error');
        }
        return;
      }
      startCooldown(60);
      setOTPState(OTP_STATE.CODE_SENT);
      setVerifyStatus('Code sent to ' + email, 'success');
    } catch (err) {
      setOTPState(OTP_STATE.UNVERIFIED);
      setVerifyStatus('Unable to connect. Please check your internet connection and try again.', 'error');
    }
  }

  async function verifyOTP() {
    const email = emailInput.value.trim().toLowerCase();
    const code = otpInput.value.trim();
    if (!code || code.length !== 6) {
      otpError.textContent = 'Please enter the 6-digit code';
      return;
    }
    otpError.textContent = '';
    setOTPState(OTP_STATE.VERIFYING);
    try {
      const res = await fetch(`${API_GATEWAY_URL}/verify-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, otp: code })
      });
      const data = await res.json();
      if (!res.ok) {
        otpSubmitBtn.disabled = false;
        otpSubmitBtn.textContent = 'Verify code';
        otpState = OTP_STATE.CODE_SENT;
        otpError.textContent = data.message || 'Invalid code. Please try again.';
        return;
      }
      setOTPState(OTP_STATE.VERIFIED);
    } catch (err) {
      otpSubmitBtn.disabled = false;
      otpSubmitBtn.textContent = 'Verify code';
      otpState = OTP_STATE.CODE_SENT;
      otpError.textContent = 'Unable to connect. Please try again.';
    }
  }

  // Section visibility helpers
  function showSection(s) { s.removeAttribute('hidden'); }
  function hideSection(s) { s.setAttribute('hidden', ''); }
  function showLoading() { hideSection(form.closest('.vmb-form-section')); hideSection(resultsSection); hideSection(errorSection); showSection(loadingSection); }
  function showResults(summary, url, originalFilename) {
    hideSection(loadingSection); hideSection(errorSection); hideSection(form.closest('.vmb-form-section'));
    summaryText.textContent = summary;
    const now = new Date();
    const dateStr = now.getFullYear().toString()
      + String(now.getMonth() + 1).padStart(2, '0')
      + String(now.getDate()).padStart(2, '0');
    const accountName = (companyInput.value.trim() || 'Report').replace(/[^a-zA-Z0-9_-]/g, '_');
    const downloadFilename = `SlashedReport_${dateStr}_${accountName}.pdf`;
    fetch(url)
      .then(r => r.blob())
      .then(blob => {
        const blobUrl = URL.createObjectURL(blob);
        downloadLink.href = blobUrl;
        downloadLink.removeAttribute('download');
        showSection(resultsSection);
      })
      .catch(() => {
        downloadLink.href = url;
        downloadLink.removeAttribute('download');
        showSection(resultsSection);
      });
  }
  function showError(message) { hideSection(loadingSection); hideSection(resultsSection); hideSection(form.closest('.vmb-form-section')); errorMessage.textContent = message; showSection(errorSection); }
  function resetToForm() { hideSection(errorSection); hideSection(resultsSection); hideSection(loadingSection); showSection(form.closest('.vmb-form-section')); submitBtn.disabled = false; updateSubmitState(); }

  function getErrorMessage(error, context) {
    if (error.name === 'AbortError') return 'Request timed out. Please try again';
    if (!error.status) return context === 'upload' ? 'Upload failed. Please check your connection and try again' : 'Analysis failed. Please check your connection and try again';
    return 'Something went wrong. Please try again';
  }

  async function parseErrorResponse(response) {
    try { const data = await response.json(); if (data && data.message) return data.message; } catch (_) {}
    if (response.status === 429) return 'Service is busy. Please wait a moment and try again';
    if (response.status === 503) return 'Analysis is taking longer than expected. Please try again — smaller bills process faster';
    if (response.status >= 500) return 'Something went wrong. Please try again';
    return 'Something went wrong. Please try again';
  }

  async function uploadFile(contactInfo, file) {
    const formData = new FormData();
    formData.append('name', contactInfo.name);
    formData.append('company', contactInfo.company);
    formData.append('email', contactInfo.email);
    formData.append('phone', contactInfo.phone);
    formData.append('file', file);
    const response = await fetch(`${API_GATEWAY_URL}/upload`, { method: 'POST', body: formData });
    if (!response.ok) { const msg = await parseErrorResponse(response); throw Object.assign(new Error(msg), { status: response.status, userMessage: msg }); }
    return response.json();
  }

  async function analyzeFile(sessionId, email) {
    // Start analysis — may return 200 (complete), 202 (processing), or 503 (API Gateway timeout but Lambda still running)
    var response;
    try {
      response = await fetch(API_GATEWAY_URL + '/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sessionId: sessionId, email: email }) });
    } catch (e) {
      // Network error — start polling anyway in case Lambda is running
      response = null;
    }

    if (response && response.ok) {
      try {
        var data = await response.json();
        if (data.status === 'complete') return data;
      } catch (e) { /* ignore parse error, start polling */ }
    }

    // If we got 400/404, that's a real error — don't poll
    if (response && response.status >= 400 && response.status < 500) {
      var msg = await parseErrorResponse(response);
      throw Object.assign(new Error(msg), { status: response.status, userMessage: msg });
    }

    // For 5xx (API Gateway timeout) or 202 — start polling
    // Lambda is still running in the background, result will appear in S3
    for (var i = 0; i < 120; i++) {
      await new Promise(function(r) { setTimeout(r, 5000); });
      try {
        var pollRes = await fetch(API_GATEWAY_URL + '/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sessionId: sessionId, email: email }) });
        if (pollRes.ok) {
          var pollData = await pollRes.json();
          if (pollData.status === 'complete') return pollData;
        }
        // 202 = still processing, 5xx = Lambda still running, keep polling
        if (pollRes.status >= 400 && pollRes.status < 500) {
          var errMsg = await parseErrorResponse(pollRes);
          throw Object.assign(new Error(errMsg), { status: pollRes.status, userMessage: errMsg });
        }
      } catch (e) {
        if (e.userMessage) throw e; // re-throw 4xx errors
        // Network errors — keep polling
      }
    }
    throw Object.assign(new Error('Analysis timed out'), { userMessage: 'Analysis is taking too long. Please try again with a smaller bill.' });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const contactInfo = {
      name: nameInput.value.trim(),
      company: companyInput.value.trim(),
      email: emailInput.value.trim(),
      phone: phoneInput.value.trim()
    };
    const file = fileInput.files[0];
    if (!contactInfo.name || !contactInfo.company || !contactInfo.email || !contactInfo.phone || !file) return;
    submitBtn.disabled = true;
    showLoading();
    try {
      const uploadResult = await uploadFile(contactInfo, file);
      const analyzeResult = await analyzeFile(uploadResult.sessionId, contactInfo.email);
      showResults(analyzeResult.summary, analyzeResult.downloadUrl, analyzeResult.originalFilename);
      // Sync billing data to lead record
      try {
        fetch(`${API_GATEWAY_URL}/admin/leads/sync-billing`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({email: contactInfo.email, sessionId: uploadResult.sessionId, timestamp: uploadResult.timestamp || ''})
        });
      } catch(e) { /* non-critical */ }
    } catch (error) {
      const msg = error.userMessage || getErrorMessage(error, 'upload');
      showError(msg);
    }
  }

  // Prevent drag-and-drop when unverified
  filePickerWrapper.addEventListener('dragover', (e) => {
    if (otpState !== OTP_STATE.VERIFIED) { e.preventDefault(); e.stopPropagation(); }
  });
  filePickerWrapper.addEventListener('drop', (e) => {
    if (otpState !== OTP_STATE.VERIFIED) { e.preventDefault(); e.stopPropagation(); }
  });

  // Event listeners
  nameInput.addEventListener('input', validateName);
  nameInput.addEventListener('blur', validateName);
  companyInput.addEventListener('input', validateCompany);
  companyInput.addEventListener('blur', validateCompany);
  emailInput.addEventListener('input', validateEmail);
  emailInput.addEventListener('blur', validateEmail);
  phoneInput.addEventListener('input', validatePhone);
  phoneInput.addEventListener('blur', validatePhone);
  fileInput.addEventListener('change', validateFile);
  form.addEventListener('submit', handleSubmit);
  retryBtn.addEventListener('click', resetToForm);

  // OTP event listeners
  verifyBtn.addEventListener('click', sendOTP);
  otpSubmitBtn.addEventListener('click', verifyOTP);
  otpInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); verifyOTP(); } });
  resendLink.addEventListener('click', (e) => { e.preventDefault(); if (cooldownRemaining <= 0) sendOTP(); });

  // Initialize
  updateFilePickerState();
  updateVerifyButton();
});


// ============================================================
// Marketing Pipeline — Offer Wall Logic
// ============================================================

(function initPipeline() {
    // Extract savings amount from AI summary text
    function extractSavings(summaryText) {
        if (!summaryText) return null;
        // Match patterns like "$1,234", "$1.2K", "$12,345/month"
        var patterns = [
            /\$([0-9,]+(?:\.[0-9]+)?)\s*(?:\/month|per month|monthly|\/mo)/i,
            /save\s+\$([0-9,]+(?:\.[0-9]+)?)/i,
            /savings?\s+of\s+\$([0-9,]+(?:\.[0-9]+)?)/i,
            /\$([0-9,]+(?:\.[0-9]+)?)\s+(?:in\s+)?(?:potential\s+)?savings/i,
            /\$([0-9,]+(?:\.[0-9]+)?)/,
        ];
        for (var i = 0; i < patterns.length; i++) {
            var m = summaryText.match(patterns[i]);
            if (m) {
                var val = parseFloat(m[1].replace(/,/g, ''));
                if (!isNaN(val) && val > 0) return val;
            }
        }
        return null;
    }

    // Format savings for display
    function formatSavings(amount) {
        if (amount >= 1000) return '$' + (amount / 1000).toFixed(1) + 'K';
        return '$' + Math.round(amount).toLocaleString();
    }

    // Calculate service price: min($299, 20% of savings)
    function calcServicePrice(savings) {
        if (!savings) return '$299';
        var pct = Math.round(savings * 0.20);
        var price = Math.min(299, pct);
        return '$' + price;
    }

    // Override showResults to also trigger the offer wall
    var _origShowResults = window._pipelineShowResults;

    // Hook into the results display
    var _origSummaryEl = null;
    var _pipelineEmail = null;
    var _pipelineSavings = null;

    // Intercept the summary text being set to extract savings
    var summaryObserver = null;
    function watchSummary() {
        var summaryEl = document.getElementById('vmb-summary');
        if (!summaryEl) return;
        summaryObserver = new MutationObserver(function() {
            var text = summaryEl.textContent || '';
            if (text) {
                _pipelineSavings = extractSavings(text);
                updateOfferWall(_pipelineSavings);
            }
        });
        summaryObserver.observe(summaryEl, { childList: true, characterData: true, subtree: true });
    }

    function updateOfferWall(savings) {
        // Show savings banner
        var banner = document.getElementById('vmb-savings-banner');
        var savingsVal = document.getElementById('vmb-savings-value');
        if (banner && savings && savings > 50) {
            savingsVal.textContent = formatSavings(savings) + '/month';
            banner.style.display = 'block';
        }

        // Update service price
        var priceEl = document.getElementById('vmb-service-price');
        var priceNote = document.getElementById('vmb-service-price-note');
        if (priceEl && savings) {
            var price = calcServicePrice(savings);
            priceEl.textContent = price;
            if (priceNote) {
                var pct = Math.round(savings * 0.20);
                if (pct < 299) {
                    priceNote.textContent = '20% of your ' + formatSavings(savings) + ' savings';
                } else {
                    priceNote.textContent = 'flat fee — capped at $299';
                }
            }
        }
    }

    // Get the verified email from the OTP flow
    function getVerifiedEmail() {
        // The email is stored in verifiedEmail variable in the main closure
        // We read it from the input since it's verified at that point
        var emailInput = document.getElementById('vmb-email');
        return emailInput ? emailInput.value.trim().toLowerCase() : '';
    }

    // Wire up "Join as Member" button
    document.addEventListener('DOMContentLoaded', function() {
        watchSummary();

        var joinBtn = document.getElementById('vmb-join-member');
        if (joinBtn) {
            joinBtn.onclick = function() {
                var email = getVerifiedEmail();
                var savings = _pipelineSavings;
                // Redirect to member portal with email pre-filled
                var url = '../members/?email=' + encodeURIComponent(email);
                if (savings) url += '&savings=' + Math.round(savings);
                url += '&source=bill-check';
                // Tag the lead
                _tagLead(email, 'member-signup', savings);
                window.location.href = url;
            };
        }

        // Wire up "Book Consultation" button
        var bookBtn = document.getElementById('vmb-book-service');
        if (bookBtn) {
            bookBtn.onclick = function() {
                var wrapper = document.getElementById('vmb-consult-form-wrapper');
                if (wrapper) {
                    wrapper.style.display = 'block';
                    wrapper.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
                _tagLead(getVerifiedEmail(), 'consultation-interest', _pipelineSavings);
            };
        }

        // Cancel consultation form
        var cancelBtn = document.getElementById('vmb-consult-cancel');
        if (cancelBtn) {
            cancelBtn.onclick = function() {
                var wrapper = document.getElementById('vmb-consult-form-wrapper');
                if (wrapper) wrapper.style.display = 'none';
            };
        }

        // Consultation form submit
        var consultForm = document.getElementById('vmb-consult-form');
        if (consultForm) {
            consultForm.onsubmit = async function(e) {
                e.preventDefault();
                var statusEl = document.getElementById('vmb-consult-status');
                var submitBtn = consultForm.querySelector('[type=submit]');
                var email = getVerifiedEmail();
                var method = (consultForm.querySelector('[name=contact_method]:checked') || {}).value || 'email';
                var notes = (document.getElementById('vmb-consult-notes') || {}).value || '';

                submitBtn.disabled = true;
                submitBtn.querySelector('span').textContent = 'Sending...';

                try {
                    // Send to the contact form / leads endpoint
                    await fetch(API_GATEWAY_URL + '/send-otp', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            email: email,
                            type: 'consultation-request',
                            contactMethod: method,
                            notes: notes,
                            savings: _pipelineSavings,
                        })
                    });
                    statusEl.className = 'vmb-consult-status success';
                    statusEl.textContent = '✓ Request sent! We\'ll be in touch within 24 hours.';
                    submitBtn.querySelector('span').textContent = 'Sent!';
                    _tagLead(email, 'consultation-booked', _pipelineSavings);
                } catch (err) {
                    statusEl.className = 'vmb-consult-status error';
                    statusEl.textContent = 'Failed to send. Please email us at info@slashmycloudbill.com';
                    submitBtn.disabled = false;
                    submitBtn.querySelector('span').textContent = 'Send Request';
                }
            };
        }
    });

    // Tag lead with pipeline stage
    function _tagLead(email, stage, savings) {
        if (!email) return;
        try {
            fetch(API_GATEWAY_URL + '/admin/leads/sync-billing', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: email,
                    pipelineStage: stage,
                    potentialSavings: savings || 0,
                    timestamp: new Date().toISOString(),
                })
            });
        } catch (e) { /* non-critical */ }
    }

})();
