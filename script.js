// Contact Form Handler
document.addEventListener('DOMContentLoaded', () => {
    const contactForm = document.getElementById('contact-form');
    const formStatus = document.getElementById('form-status');
    
    if (contactForm) {
        contactForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            // Get form data
            const formData = {
                name: document.getElementById('name').value,
                email: document.getElementById('email').value,
                phone: document.getElementById('phone').value || 'Not provided',
                company: document.getElementById('company').value || 'Not provided',
                message: document.getElementById('message').value
            };
            
            // Show loading state
            formStatus.className = 'form-status loading';
            formStatus.textContent = 'Sending your message...';
            
            try {
                // API Gateway endpoint for contact form
                const apiEndpoint = 'https://nyppohkc65.execute-api.us-east-1.amazonaws.com/prod/contact';
                
                const response = await fetch(apiEndpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(formData)
                });
                
                if (response.ok) {
                    // Success
                    formStatus.className = 'form-status success';
                    formStatus.textContent = '✓ Message sent successfully! We\'ll get back to you soon.';
                    contactForm.reset();
                    
                    // Hide success message after 5 seconds
                    setTimeout(() => {
                        formStatus.style.display = 'none';
                    }, 5000);
                } else {
                    throw new Error('Failed to send message');
                }
            } catch (error) {
                // Error
                formStatus.className = 'form-status error';
                formStatus.textContent = '✗ Failed to send message. Please try again or email us directly.';
                console.error('Form submission error:', error);
            }
        });
    }
});
