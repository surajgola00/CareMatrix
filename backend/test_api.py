import requests

BASE_URL = "http://127.0.0.1:8000"

def print_step(title):
    print(f"\n===== {title} =====")

# =========================
# 1. REGISTER HOSPITALS
# =========================
print_step("Register Hospitals")

h1 = requests.post(f"{BASE_URL}/api/hospital/register", json={
    "name": "City Hospital",
    "lat": 28.61,
    "lng": 77.20
}).json()

h2 = requests.post(f"{BASE_URL}/api/hospital/register", json={
    "name": "Apollo Hospital",
    "lat": 28.62,
    "lng": 77.21
}).json()

hospital1 = h1["id"]
hospital2 = h2["id"]

print("Hospital1:", hospital1)
print("Hospital2:", hospital2)

# =========================
# 2. UPDATE CAPACITY
# =========================
print_step("Update Capacity")

requests.post(f"{BASE_URL}/api/hospital/capacity", json={
    "hospital_id": hospital1,
    "department": "ICU",
    "total": 10,
    "available": 5
})

requests.post(f"{BASE_URL}/api/hospital/capacity", json={
    "hospital_id": hospital2,
    "department": "ICU",
    "total": 8,
    "available": 3
})

print("Capacity updated")

# =========================
# 3. CREATE PATIENT REQUEST
# =========================
print_step("Create Patient Request")

patient = requests.post(f"{BASE_URL}/api/request", json={
    "department": "ICU",
    "priority": "high",
    "lat": 28.60,
    "lng": 77.19
}).json()

patient_id = patient["patient_id"]
print("Patient ID:", patient_id)

# =========================
# 4. FETCH OPEN REQUESTS
# =========================
print_step("Fetch Open Requests")

open_requests = requests.get(f"{BASE_URL}/api/hospital/open-requests").json()
print("Open Requests:", open_requests)

# =========================
# 5. HOSPITAL RESPONDS
# =========================
print_step("Hospital Responds")

requests.post(f"{BASE_URL}/api/hospital/respond", json={
    "patient_id": patient_id,
    "hospital_id": hospital1,
    "status": "accepted"
})

requests.post(f"{BASE_URL}/api/hospital/respond", json={
    "patient_id": patient_id,
    "hospital_id": hospital2,
    "status": "accepted"
})

print("Responses sent")

# =========================
# 6. GET RESPONSES
# =========================
print_step("Get Patient Responses")

responses = requests.get(
    f"{BASE_URL}/api/patient/responses",
    params={"patient_id": patient_id}
).json()

print("Responses:", responses)

# =========================
# 7. SELECT HOSPITAL
# =========================
print_step("Select Hospital")

select = requests.post(f"{BASE_URL}/api/patient/select", json={
    "patient_id": patient_id,
    "hospital_id": hospital1
}).json()

print("Selection Result:", select)

# =========================
# 8. GET FINAL RESULT
# =========================
print_step("Get Final Result")

result = requests.get(
    f"{BASE_URL}/api/getResult",
    params={"patient_id": patient_id}
).json()

print("Final Result:", result)

# =========================
# 9. RESOURCE REQUEST FLOW
# =========================
print_step("Resource Request")

res_req = requests.post(f"{BASE_URL}/api/resource/request", json={
    "hospital_id": hospital1,
    "resource_type": "oxygen",
    "quantity": 5
}).json()

request_id = res_req["request_id"]
print("Resource Request ID:", request_id)

# =========================
# 10. GET OPEN RESOURCE REQUESTS
# =========================
print_step("Get Open Resource Requests")

open_res = requests.get(f"{BASE_URL}/api/resource/open").json()
print(open_res)

# =========================
# 11. RESPOND TO RESOURCE
# =========================
print_step("Respond to Resource")

requests.post(f"{BASE_URL}/api/resource/respond", json={
    "request_id": request_id,
    "hospital_id": hospital2,
    "status": "accepted"
})

print("Resource response sent")

# =========================
# 12. GET RESOURCE RESPONSES
# =========================
print_step("Get Resource Responses")

res_responses = requests.get(
    f"{BASE_URL}/api/resource/responses",
    params={"request_id": request_id}
).json()

print(res_responses)

# =========================
# 13. SELECT RESOURCE PROVIDER
# =========================
print_step("Select Resource Provider")

final_res = requests.post(f"{BASE_URL}/api/resource/select", json={
    "request_id": request_id,
    "hospital_id": hospital2
}).json()

print("Final Resource Status:", final_res)

# =========================
# 14. HEATMAP
# =========================
print_step("Heatmap")

heatmap = requests.get(f"{BASE_URL}/api/heatmap").json()
print(heatmap)

# =========================
# 15. DEBUG STATE
# =========================
print_step("Debug State")

debug = requests.get(f"{BASE_URL}/api/debug/state").json()
print(debug)

print("\n✅ ALL TESTS COMPLETED")