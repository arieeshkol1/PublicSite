// Contact Form Handler
document.addEventListener('DOMContentLoaded', () => {
    const contactForm = document.getElementById('contact-form');
    const formStatus = document.getElementById('form-status');
    
    if (contactForm) {
        contactForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(contactForm);
            
            // Show loading state
            formStatus.className = 'form-status loading';
            formStatus.textContent = 'Sending your message...';
            
            try {
                const response = await fetch('https://formsubmit.co/ajax/ariel.eshkol@gmail.com', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({
                        name: formData.get('name'),
                        email: formData.get('email'),
                        phone: formData.get('phone') || 'Not provided',
                        company: formData.get('company') || 'Not provided',
                        message: formData.get('message'),
                        _subject: 'New Contact from eshkolai.com',
                        _template: 'table'
                    })
                });
                
                const data = await response.json();
                
                if (data.success === 'true' || response.ok) {
                    formStatus.className = 'form-status success';
                    formStatus.textContent = '✓ Message sent! We\'ll get back to you soon.';
                    contactForm.reset();
                    setTimeout(() => { formStatus.style.display = 'none'; }, 5000);
                } else {
                    throw new Error('Send failed');
                }
            } catch (error) {
                formStatus.className = 'form-status error';
                formStatus.textContent = '✗ Failed to send. Please email us directly at ariel.eshkol@gmail.com';
                console.error('Form error:', error);
            }
        });
    }
});
