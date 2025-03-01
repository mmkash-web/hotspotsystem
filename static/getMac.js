async function getUserIP() {
    try {
        let response = await fetch("https://api64.ipify.org?format=json");
        let data = await response.json();
        document.getElementById("ipAddress").value = data.ip;
    } catch (error) {
        console.error("Error getting IP:", error);
    }
}

async function fetchMacAddress() {
    let ip = await getUserIP();
    let response = await fetch("http://ec32-154-159-252-52.ngrok-free.app/map-mac", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ip: ip })
    });

    let macData = await response.json();
    if (macData.mac) {
        document.getElementById("macAddress").value = macData.mac;
    }
}

document.getElementById("package").addEventListener("change", function() {
    let selectedOption = this.options[this.selectedIndex];
    document.getElementById("profile").value = selectedOption.dataset.profile;
});

fetchMacAddress();
