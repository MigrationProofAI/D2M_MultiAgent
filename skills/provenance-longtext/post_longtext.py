import sys, json, requests, os

material = sys.argv[1]
language = sys.argv[2]
entity   = sys.argv[3]
text     = sys.argv[4]

base = os.environ.get('SAP_BASE_URL', 'https://vhcals4hci.dummy.nodomain:44301')
url  = f"{base}/sap/opu/odata/sap/API_PRODUCT_SRV/{entity}"

headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

payload = {
    'Product': material,
    'Language': language,
    'LongText': text
}

auth = (
    os.environ.get('SAP_USER', 'DEVELOPER'),
    os.environ.get('SAP_PASS', 'ABAPtr1909!')
)

resp = requests.post(url, json=payload, headers=headers, auth=auth, verify=False)
print(json.dumps({'status': resp.status_code, 'body': resp.text[:500]}))
