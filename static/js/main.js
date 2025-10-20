// static/js/main.js

document.addEventListener("DOMContentLoaded", function() {
    
    // --- Logout Logic ---
    // This function will handle the logout process
    const handleLogout = () => {
        fetch('/users/logout', {
            method: 'POST',
        })
        .then(response => {
            if (response.ok) {
                // Redirect to home page on successful logout
                window.location.href = '/';
            } else {
                console.error('Logout request failed!');
            }
        })
        .catch(error => console.error('Error during logout:', error));
    };

    // Select both the desktop and mobile logout buttons
    const desktopLogoutBtn = document.getElementById('logoutBtn');
    const mobileLogoutBtn = document.getElementById('mobileLogout');

    // Attach the click event listener to the desktop button if it exists
    if (desktopLogoutBtn) {
        desktopLogoutBtn.addEventListener('click', function(event) {
            event.preventDefault();
            handleLogout();
        });
    }

    // Attach the click event listener to the mobile button if it exists
    if (mobileLogoutBtn) {
        mobileLogoutBtn.addEventListener('click', function(event) {
            event.preventDefault();
            handleLogout();
        });
    }

    // You can add other JavaScript logic for your site below
    // --- End Logout Logic ---

});