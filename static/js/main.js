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

    const patientListContainer = document.getElementById("patient-list-container");

    if (patientListContainer) {
        // This code runs only on the doctor dashboard
        fetch('/doctor/my-patients')
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(patients => {
                // Hide the loader
                const loader = document.getElementById("patient-list-loader");
                if (loader) loader.style.display = 'none';

                if (patients.length === 0) {
                    patientListContainer.innerHTML = `
                        <p class="text-center text-gray-500">
                          No connected patients yet.
                        </p>
                    `;
                    return;
                }

                // Build the patient list HTML
                let patientHtml = '<ul class="divide-y divide-gray-200">';
                patients.forEach(patient => {
                    patientHtml += `
                        <li class="py-4 flex justify-between items-center">
                          <div>
                            <p class="text-sm font-medium text-gray-900">${patient.name ? patient.name.first + ' ' + patient.name.last : 'N/A'}</p>
                            <p class="text-sm text-gray-500">${patient.email}</p>
                            <p class="text-sm text-gray-500">ID: ${patient.aarogya_id}</p>
                          </div>
                          <a href="/doctor/patient/${patient.aarogya_id}" class="text-sm font-medium text-indigo-600 hover:text-indigo-500">
                            View Records
                          </a>
                        </li>
                    `;
                });
                patientHtml += '</ul>';
                patientListContainer.innerHTML = patientHtml;
            })
            .catch(error => {
                const loader = document.getElementById("patient-list-loader");
                if (loader) loader.style.display = 'none';
                patientListContainer.innerHTML = `
                  <p class="text-center text-red-500">
                    Failed to load patient list. ${error.message}
                  </p>
                `;
            });
    }

    const patientSearchForm = document.getElementById("patientSearchForm");
    const resultsContainer = document.getElementById("search-results-container");

    if (patientSearchForm) {
        patientSearchForm.addEventListener("submit", function(event) {
            event.preventDefault();
            const formData = new FormData(patientSearchForm);
            const aarogyaId = formData.get("aarogya_id");
            
            Swal.fire({
                title: 'Searching...',
                text: `Looking for patient ${aarogyaId}`,
                didOpen: () => { Swal.showLoading(); }
            });

            fetch(`/doctor/patients/search?aarogya_id=${aarogyaId}`)
                .then(response => {
                    if (!response.ok) { return response.json().then(err => { throw err; }); }
                    return response.json();
                })
                .then(patient => {
                    Swal.close();
                    // NEW: HTML now includes a "Send Request" button
                    resultsContainer.innerHTML = `
                        <div class="bg-white p-6 rounded-2xl shadow-md">
                            <h3 class="text-xl font-semibold text-gray-900">Patient Found</h3>
                            <div class="mt-4 space-y-2">
                                <p><strong>Name:</strong> ${patient.name.first} ${patient.name.last}</p>
                                <p><strong>Email:</strong> ${patient.email}</p>
                                <p><strong>Aarogya ID:</strong> ${patient.aarogya_id}</p>
                            </div>
                            <div class="mt-6 border-t pt-4">
                                <button id="send-connection-request"
                                        data-patient-id="${patient.aarogya_id}"
                                        class="w-full inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500">
                                    Send Connection Request
                                </button>
                            </div>
                        </div>
                    `;
                })
                .catch(error => {
                    Swal.fire({
                        icon: 'error',
                        title: 'Search Failed',
                        text: error.detail || `Could not find patient with ID ${aarogyaId}.`
                    });
                    resultsContainer.innerHTML = '';
                });
        });
    }

    // --- NEW: Add this event listener to handle the "Send Request" button click ---
    if (resultsContainer) {
        // We use event delegation to listen for clicks on the container
        resultsContainer.addEventListener('click', function(event) {
            // Check if the clicked element is our "Send Request" button
            if (event.target.id === 'send-connection-request') {
                const patientId = event.target.getAttribute('data-patient-id');
                
                Swal.fire({
                    title: 'Sending Request...',
                    text: `Sending connection request to patient ${patientId}`,
                    didOpen: () => { Swal.showLoading(); }
                });

                // Call the connection API endpoint
                fetch(`/connections/request/${patientId}`, {
                    method: 'POST'
                })
                .then(response => {
                    if (!response.ok) { return response.json().then(err => { throw err; }); }
                    return response.json();
                })
                .then(data => {
                    // Success!
                    Swal.fire({
                        icon: 'success',
                        title: 'Request Sent!',
                        text: data.message || 'The patient will be notified to accept your request.'
                    });
                    // Disable the button to prevent double-sending
                    event.target.disabled = true;
                    event.target.textContent = 'Request Sent';
                    event.target.classList.add('bg-gray-400', 'hover:bg-gray-400');
                })
                .catch(error => {
                    // Error (e.g., already connected, or request already pending)
                    Swal.fire({
                        icon: 'error',
                        title: 'Could Not Send Request',
                        text: error.detail || 'An unknown error occurred.'
                    });
                });
            }
        });
    }
});