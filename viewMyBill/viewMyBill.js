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
    const response = await fetch(`${API_GATEWAY_URL}/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sessionId, email }) });
    if (!response.ok) { const msg = await parseErrorResponse(response); throw Object.assign(new Error(msg), { status: response.status, userMessage: msg }); }
    return response.json();
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
