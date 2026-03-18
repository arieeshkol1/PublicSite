/* ViewMyBill - Client-side logic for AWS bill analysis */

const API_GATEWAY_URL = 'https://l2fd4h481h.execute-api.us-east-1.amazonaws.com';

const MAX_FILE_SIZE = 10485760; // 10 MB
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_REGEX = /^[\d\s\+\-\(\)\.]{7,20}$/;

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

  // Validation state
  let nameValid = false;
  let companyValid = false;
  let emailValid = false;
  let phoneValid = false;
  let fileValid = false;

  function updateSubmitState() {
    submitBtn.disabled = !(nameValid && companyValid && emailValid && phoneValid && fileValid);
  }

  function validateName() {
    const value = nameInput.value.trim();
    if (!value) { nameValid = false; nameError.textContent = ''; }
    else if (value.length < 2) { nameValid = false; nameError.textContent = 'Name must be at least 2 characters'; }
    else { nameValid = true; nameError.textContent = ''; }
    updateSubmitState();
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
    updateSubmitState();
  }

  function validatePhone() {
    const value = phoneInput.value.trim();
    if (!value) { phoneValid = false; phoneError.textContent = ''; }
    else if (!PHONE_REGEX.test(value)) { phoneValid = false; phoneError.textContent = 'Please enter a valid phone number'; }
    else { phoneValid = true; phoneError.textContent = ''; }
    updateSubmitState();
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

  // Section visibility helpers
  function showSection(s) { s.removeAttribute('hidden'); }
  function hideSection(s) { s.setAttribute('hidden', ''); }
  function showLoading() { hideSection(form.closest('.vmb-form-section')); hideSection(resultsSection); hideSection(errorSection); showSection(loadingSection); }
  function showResults(summary, url) { hideSection(loadingSection); hideSection(errorSection); hideSection(form.closest('.vmb-form-section')); summaryText.textContent = summary; downloadLink.href = url; showSection(resultsSection); }
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
      showResults(analyzeResult.summary, analyzeResult.downloadUrl);
    } catch (error) {
      const msg = error.userMessage || getErrorMessage(error, 'upload');
      showError(msg);
    }
  }

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
});
