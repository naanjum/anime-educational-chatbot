document.addEventListener('DOMContentLoaded', function() {
    const container = document.getElementById('container');
    const registerBtn = document.getElementById('register');
    const loginBtn = document.getElementById('login');
    const signUpForm = document.querySelector('.sign-up form');
    const signInForm = document.querySelector('.sign-in form');

    registerBtn.addEventListener('click', () => {
        container.classList.add("active");
    });

    loginBtn.addEventListener('click', () => {
        container.classList.remove("active");
    });

    // Clear error messages when switching forms
    const clearErrors = () => {
        const errorMessages = document.querySelectorAll('.error-message');
        errorMessages.forEach(error => error.remove());
    };

    registerBtn.addEventListener('click', clearErrors);
    loginBtn.addEventListener('click', clearErrors);

    // Form validation
    signUpForm.addEventListener('submit', function(e) {
        const password = this.querySelector('input[name="password"]').value;
        if (password.length < 6) {
            e.preventDefault();
            showError('Password must be at least 6 characters long');
        }
    });

    signInForm.addEventListener('submit', function(e) {
        const email = this.querySelector('input[name="email"]').value;
        const password = this.querySelector('input[name="password"]').value;
        
        if (!email || !password) {
            e.preventDefault();
            showError('Please fill in all fields');
        }
    });

    function showError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = message;
        
        const activeForm = container.classList.contains('active') ? 
            document.querySelector('.sign-up form') : 
            document.querySelector('.sign-in form');
            
        const existingError = activeForm.querySelector('.error-message');
        if (existingError) {
            existingError.remove();
        }
        
        activeForm.insertBefore(errorDiv, activeForm.firstChild);
    }
}); 