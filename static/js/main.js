document.addEventListener("DOMContentLoaded", function() {

    // --- Universal Form Handling Logic ---
    const handleFormSubmit = (formElement) => {
        if (!formElement) return;

        formElement.addEventListener("submit", function(event) {
            event.preventDefault();
            const formData = new FormData(formElement);
            
            fetch(formElement.action, {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => { throw err; });
                }
                return response.json();
            })
            .then(data => {
                Swal.fire({
                    icon: 'success',
                    title: 'Success!',
                    text: data.message || 'Your request was successful.',
                    timer: 2000,
                    showConfirmButton: false
                }).then(() => {
                    // Smart redirect based on user type
                    if (data.user_type === 'doctor') {
                        window.location.href = '/doctor/dashboard';
                    } else {
                        window.location.href = '/profile'; // Default for patients
                    }
                });
            })
            .catch(error => {
                Swal.fire({
                    icon: 'error',
                    title: 'Oops...',
                    text: error.detail || 'An unknown error occurred. Please check your input and try again.'
                });
            });
        });
    };

    // Attach the handler to all three forms
    handleFormSubmit(document.getElementById("loginForm"));
    handleFormSubmit(document.getElementById("registerForm"));
    handleFormSubmit(document.getElementById("registerDoctorForm"));


    // --- Logout Button Logic ---
    const handleLogout = () => {
        fetch('/users/logout', { method: 'POST' })
            .then(response => {
                if (response.ok) window.location.href = '/';
            });
    };

    const desktopLogoutBtn = document.getElementById('logoutBtn');
    if (desktopLogoutBtn) desktopLogoutBtn.addEventListener('click', handleLogout);

    const mobileLogoutBtn = document.getElementById('mobileLogout');
    if (mobileLogoutBtn) mobileLogoutBtn.addEventListener('click', handleLogout);
});