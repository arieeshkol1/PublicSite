/* ViewMyBill - Client-side logic for AWS bill analysis */

const API_GATEWAY_URL = 'https://YOUR_API_GATEWAY_URL';

const MAX_FILE_SIZE = 10485760; // 10 MB
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

document.addEventListener('DOMContentLoaded', () => {
  // DOM references
  const form = document.getElementById('vmb-form');
  const emailInput = document.getElementById('vmb-email');
  const emailError = document.getElementById('vmb-email-error');
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
  let emailValid = false;
  let fileValid = false;

  // --- Validation helpers ---

  function validateEmail() {
    const value = emailInput.value.trim();
    if (!value) {
      emailValid = false;
      emailError.textContent = '';
      return;
    }
    if (!EMAIL_REGEX.test(value)) {
      emailValid = false;
      emailError.textContent = 'Please enter a valid email address';
    } else {
      emailValid = true;
      emailError.textContent = '';
    }
    updateSubmitState();
  }

  function validateFile() {
    const file = fileInput.files[0];
    fileError.textContent = '';
    filenameDisplay.textContent = '';

    if (!file) {
      fileValid = false;
      updateSubmitState();
      return;
    }

    const name = file.name;
    const ext = name.substring(name.lastIndexOf('.')).toLowerCase();

    if (ext !== '.pdf') {
      fileValid = false;
      fileError.textContent = 'Only PDF files are supported';
      fileInput.value = '';
      updateSubmitState();
      return;
    }

    if (file.size === 0) {
      fileValid = false;
      fileError.textContent = 'The selected file is empty';
      fileInput.value = '';
      updateSubmitState();
      return;
    }

    if (file.size > MAX_FILE_SIZE) {
      fileValid = false;
      fileError.textContent = 'File exceeds 10 MB limit. Please upload a smaller file';
      fileInput.value = '';
      updateSubmitState();
      return;
    }

    fileValid = true;
    filenameDisplay.textContent = name;
    updateSubmitState();
  }

  function updateSubmitState() {
    submitBtn.disabled = !(emailValid && fileValid);
  }

  // --- Section visibility helpers ---

  function showSection(section) {
    section.removeAttribute('hidden');
  }

  function hideSection(section) {
    section.setAttribute('hidden', '');
  }

  function showLoading() {
    hideSection(form.closest('.vmb-form-section'));
    hideSection(resultsSection);
    hideSection(errorSection);
    showSection(loadingSection);
  }

  function showResults(summary, url) {
    hideSection(loadingSection);
    hideSection(errorSection);
    hideSection(form.closest('.vmb-form-section'));
    summaryText.textContent = summary;
    downloadLink.href = url;
    showSection(resultsSection);
  }

  function showError(message) {
    hideSection(loadingSection);
    hideSection(resultsSection);
    hideSection(form.closest('.vmb-form-section'));
    errorMessage.textContent = message;
    showSection(errorSection);
  }

  function resetToForm() {
    hideSection(errorSection);
    hideSection(resultsSection);
    hideSection(loadingSection);
    showSection(form.closest('.vmb-form-section'));
    submitBtn.disabled = false;
    updateSubmitState();
  }

  // --- Error message helpers ---

  function getErrorMessage(error, context) {
    if (error.name === 'AbortError') {
      return 'Request timed out. Please try again';
    }
    if (!error.status) {
      return context === 'upload'
        ? 'Upload failed. Please check your connection and try again'
        : 'Analysis failed. Please check your connection and try again';
    }
    return 'Something went wrong. Please try again';
  }

  async function parseErrorResponse(response) {
    try {
      const data = await response.json();
      if (data && data.message) return data.message;
    } catch (_) {
      // ignore parse errors
    }
    if (response.status === 429) return 'Service is busy. Please wait a moment and try again';
    if (response.status >= 500) return 'Something went wrong. Please try again';
    return 'Something went wrong. Please try again';
  }

  // --- API calls ---

  async function uploadFile(email, file) {
    const formData = new FormData();
    formData.append('email', email);
    formData.append('file', file);

    const response = await fetch(`${API_GATEWAY_URL}/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const msg = await parseErrorResponse(response);
      throw Object.assign(new Error(msg), { status: response.status, userMessage: msg });
    }

    return response.json();
  }

  async function analyzeFile(sessionId, email) {
    const response = await fetch(`${API_GATEWAY_URL}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId, email }),
    });

    if (!response.ok) {
      const msg = await parseErrorResponse(response);
      throw Object.assign(new Error(msg), { status: response.status, userMessage: msg });
    }

    return response.json();
  }

  // --- Form submission ---

  async function handleSubmit(e) {
    e.preventDefault();

    const email = emailInput.value.trim();
    const file = fileInput.files[0];
    if (!email || !file) return;

    submitBtn.disabled = true;
    showLoading();

    try {
      const uploadResult = await uploadFile(email, file);
      const analyzeResult = await analyzeFile(uploadResult.sessionId, email);
      showResults(analyzeResult.summary, analyzeResult.downloadUrl);
    } catch (error) {
      const msg = error.userMessage || getErrorMessage(error, 'upload');
      showError(msg);
    }
  }

  // --- Event listeners ---

  emailInput.addEventListener('input', validateEmail);
  emailInput.addEventListener('blur', validateEmail);
  fileInput.addEventListener('change', validateFile);
  form.addEventListener('submit', handleSubmit);
  retryBtn.addEventListener('click', resetToForm);
});
