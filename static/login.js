document.getElementById("paymentForm").addEventListener("submit", async function(event) {
    event.preventDefault();

    let phone = document.getElementById("phone").value.trim();
    let packageAmount = document.getElementById("package").value;
    let mac = document.getElementById("macAddress").value.trim();
    let ip = document.getElementById("ipAddress").value.trim();
    let profile = document.getElementById("profile").value.trim();

    if (!phone || !packageAmount || !mac || !ip || !profile) {
        document.getElementById("message").innerText = "Please fill in all required fields.";
        return;
    }

    // Delay showing the loading animation by 4 seconds
    setTimeout(() => {
        document.getElementById("loading").style.display = "block"; // Show loading animation
    }, 4000);

    try {
        let logResponse = await fetch("/log-user", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phone, mac, ip, profile })
        });

        if (!logResponse.ok) {
            throw new Error("Failed to log user details.");
        }

        let payResponse = await fetch("/pay", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phone, packageAmount })
        });

        let result;
        let clonedResponse = payResponse.clone();
        try {
            result = await payResponse.json();
        } catch (jsonError) {
            let responseText = await clonedResponse.text();
            throw new Error("The server returned an unexpected response. It might be an HTML error page. Response: " + responseText);
        }

        if (result.success) {
            // Display a success message
            document.getElementById("message").innerText = "Payment successful! You are now logged in.";
        } else {
            document.getElementById("message").innerText = "Payment failed! " + (result.message || "Try again.");
        }
    } catch (error) {
        document.getElementById("message").innerText = "Error processing payment: " + error.message;
        console.error("Payment Error:", error);
    } finally {
        // Hide loading animation (in case it was shown)
        document.getElementById("loading").style.display = "none";
    }
});
