// --- GLOBAL ACTIONS ---

window.activateLink = (apptId) => {
    if (!apptId) return;
    Swal.fire({
        title: 'Activate Link?',
        text: "Patient will be able to join the call.",
        icon: 'question',
        showCancelButton: true,
        confirmButtonText: 'Yes, Activate'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch(`/appointments/activate/${apptId}`, { method: 'POST' })
                .then(res => {
                    if (res.ok) {
                        Swal.fire('Activated!', 'Link is live.', 'success');
                        loadAppointmentsList('doctor');
                    } else {
                        Swal.fire('Error', 'Could not activate.', 'error');
                    }
                });
        }
    });
};

// NEW: Complete Appointment Function
window.completeAppointment = (apptId) => {
    if (!apptId) return;
    Swal.fire({
        title: 'Complete Appointment?',
        text: "This will mark the session as finished and deactivate the link.",
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Yes, Complete',
        confirmButtonColor: '#3085d6'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch(`/appointments/complete/${apptId}`, { method: 'POST' })
                .then(res => {
                    if (res.ok) {
                        Swal.fire('Completed!', 'Appointment closed.', 'success');
                        loadAppointmentsList('doctor');
                    } else {
                        Swal.fire('Error', 'Could not complete appointment.', 'error');
                    }
                });
        }
    });
};

document.addEventListener("DOMContentLoaded", function() {

    // --- FORM HANDLING ---
    const handleFormSubmit = (formElement) => {
        if (!formElement) return;
        formElement.addEventListener("submit", function(event) {
            event.preventDefault();
            const formData = new FormData(formElement);
            const body = new URLSearchParams(formData);

            fetch(formElement.action, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: body
            })
            .then(response => {
                if (!response.ok) return response.json().then(err => { throw err; });
                return response.json();
            })
            .then(data => {
                Swal.fire({
                    icon: 'success',
                    title: 'Success!',
                    text: data.message || 'Operation successful!',
                    timer: 2000,
                    showConfirmButton: false
                }).then(() => {
                    if (data.user_type === 'doctor') window.location.href = '/doctor/dashboard';
                    else window.location.href = '/profile';
                });
            })
            .catch(error => {
                Swal.fire({ icon: 'error', title: 'Error', text: error.detail || 'An error occurred.' });
            });
        });
    };

    handleFormSubmit(document.getElementById("loginForm"));
    handleFormSubmit(document.getElementById("registerForm"));
    handleFormSubmit(document.getElementById("registerDoctorForm"));

    // --- LOGOUT ---
    const handleLogout = () => {
        fetch('/users/logout', { method: 'POST' }).then(res => { if (res.ok) window.location.href = '/'; });
    };
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) logoutBtn.addEventListener('click', handleLogout);
    const mobileLogout = document.getElementById('mobileLogout');
    if (mobileLogout) mobileLogout.addEventListener('click', handleLogout);

    // --- DOCTOR: MY PATIENTS LIST ---
    const patientListContainer = document.getElementById("patient-list-container");
    if (patientListContainer) {
        fetch('/doctor/my-patients').then(res => res.json()).then(patients => {
            document.getElementById("patient-list-loader").style.display = 'none';
            if (!patients || patients.length === 0) {
                patientListContainer.innerHTML = '<p class="text-center text-gray-500">No connected patients.</p>';
                return;
            }
            let html = '<ul class="divide-y divide-gray-200">';
            patients.forEach(p => {
                html += `
                    <li class="py-4 flex justify-between items-center">
                      <div>
                        <p class="text-sm font-medium text-gray-900">${p.name.first} ${p.name.last}</p>
                        <p class="text-xs text-gray-400">ID: ${p.aarogya_id}</p>
                      </div>
                      <a href="/doctor/patient/${p.aarogya_id}" class="text-sm text-indigo-600 hover:text-indigo-500">View Records</a>
                    </li>`;
            });
            html += '</ul>';
            patientListContainer.innerHTML = html;
        });
    }

    // --- APPOINTMENTS LIST (SHARED) ---
    window.loadAppointmentsList = (userType) => {
        const containerId = userType === 'doctor' ? 'upcoming-appointments-container' : 'my-appointments-container';
        const loaderId = userType === 'doctor' ? 'upcoming-loader' : 'my-appt-loader';
        const container = document.getElementById(containerId);
        const loader = document.getElementById(loaderId);

        if (!container) return;

        fetch('/appointments/list').then(res => res.json()).then(data => {
            if (loader) loader.style.display = 'none';
            
            let appointmentsToShow = data;
            // Doctor: Show confirmed in "Upcoming"
            if (userType === 'doctor') {
                appointmentsToShow = data.filter(a => a.status && a.status.toLowerCase() === 'confirmed');
            }

            if (appointmentsToShow.length === 0) {
                container.innerHTML = '<p class="text-gray-500 text-center py-4">No appointments found.</p>';
                return;
            }

            container.innerHTML = ''; 
            appointmentsToShow.forEach(appt => {
                const apptId = appt.id || appt._id; 
                const dateStr = appt.appointment_time ? new Date(appt.appointment_time).toLocaleString() : 'Date Pending';
                const otherParty = userType === 'doctor' ? `Patient: ${appt.patient_email}` : `Dr. ${appt.doctor_email}`;
                
                let statusColor = 'bg-gray-100 text-gray-800';
                const statusLower = (appt.status || 'pending').toLowerCase();
                
                if (statusLower === 'confirmed') statusColor = 'bg-green-100 text-green-800';
                if (statusLower === 'rejected') statusColor = 'bg-red-100 text-red-800';
                if (statusLower === 'completed') statusColor = 'bg-blue-100 text-blue-800'; // Blue for completed

                let actionButtons = '';

                // DOCTOR ACTIONS
                if (userType === 'doctor' && statusLower === 'confirmed') {
                    // Join Button
                    actionButtons += `
                        <a href="${appt.meeting_link}" target="_blank" class="mt-2 block w-full text-center border border-green-600 text-green-600 py-2 rounded-lg text-sm hover:bg-green-50 transition-colors">
                            Join Video Call
                        </a>`;
                    
                    // Activate / Active Label
                    if (!appt.is_link_active) {
                        actionButtons += `
                            <button onclick="activateLink('${apptId}')" class="mt-2 block w-full text-center bg-indigo-600 text-white py-2 rounded-lg text-sm hover:bg-indigo-700 transition-colors">
                                Activate Link
                            </button>`;
                    } else {
                        actionButtons += `
                            <div class="mt-2 text-center text-xs text-green-700 bg-green-50 py-2 rounded border border-green-200 font-medium">
                                ✓ Link Active
                            </div>`;
                    }

                    // NEW: Complete Button
                    actionButtons += `
                        <button onclick="completeAppointment('${apptId}')" class="mt-2 block w-full text-center border border-gray-300 text-gray-700 py-2 rounded-lg text-sm hover:bg-gray-100 transition-colors">
                            Mark Completed
                        </button>`;
                }

                // PATIENT ACTIONS
                if (userType === 'patient' && statusLower === 'confirmed') {
                    if (appt.is_link_active) {
                        actionButtons += `
                            <a href="${appt.meeting_link}" target="_blank" class="mt-3 block w-full text-center bg-green-600 text-white py-2 rounded-lg text-sm hover:bg-green-700 transition-colors font-bold shadow-md animate-pulse">
                                Join Video Call
                            </a>`;
                    } else {
                        actionButtons += `
                            <div class="mt-3 block w-full text-center bg-gray-100 text-gray-500 py-2 rounded-lg text-sm border border-gray-200 cursor-not-allowed">
                                Waiting for Doctor...
                            </div>`;
                    }
                }

                const card = document.createElement('div');
                card.className = 'p-4 border rounded-xl bg-white shadow-sm hover:shadow-md transition-shadow mb-4';
                card.innerHTML = `
                    <div class="flex justify-between items-start mb-2">
                        <div>
                            <p class="font-semibold text-gray-900">${otherParty}</p>
                            <p class="text-xs text-gray-500 font-mono mt-1">Severity: ${appt.predicted_severity || 'Normal'}</p>
                        </div>
                        <span class="px-2 py-1 rounded text-xs font-bold uppercase ${statusColor}">${appt.status}</span>
                    </div>
                    <div class="text-sm text-gray-700 space-y-1 mb-3">
                        <p><strong>Reason:</strong> ${appt.reason}</p>
                        <p><span class="font-medium">Time:</span> ${dateStr}</p>
                    </div>
                    ${actionButtons}
                `;
                container.appendChild(card);
            });
        }).catch(err => { if(loader) loader.innerText = 'Error loading.'; });
    };

    if (document.getElementById('patient-appointments-view')) loadAppointmentsList('patient');
    if (document.getElementById('doctor-appointments-view')) loadAppointmentsList('doctor');
});