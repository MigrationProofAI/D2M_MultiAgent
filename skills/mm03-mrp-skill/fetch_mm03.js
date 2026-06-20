// fetch_mm03.js — MM03 Full MRP Skill fetcher
// Usage: node fetch_mm03.js <material> <plant>
// Env: SAP_BASE_URL, SAP_USER, SAP_PASS

const https = require('https');
const [,, material, plant] = process.argv;

const base = process.env.SAP_BASE_URL;
const auth = 'Basic ' + Buffer.from(`${process.env.SAP_USER}:${process.env.SAP_PASS}`).toString('base64');
const headers = { Authorization: auth, Accept: 'application/json' };

async function get(path) {
  return new Promise((resolve, reject) => {
    const url = base + path;
    https.get(url, { headers }, res => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => resolve(JSON.parse(data)));
    }).on('error', reject);
  });
}

async function fetchMM03(mat, plt) {
  const [basic, plant_data, mrp3, pv] = await Promise.all([
    get(`/sap/opu/odata/sap/API_PRODUCT_SRV/A_Product('${mat}')?$expand=to_Description($filter=Language eq 'EN')&$format=json`),
    get(`/sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductPlant(Product='${mat}',Plant='${plt}')?$format=json`),
    get(`/sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductPlantMRPArea(Product='${mat}',Plant='${plt}',MRPArea='${plt}')?$format=json`),
    get(`/sap/opu/odata/sap/API_PRODUCT_SRV/A_ProductionVersion?$filter=Product eq '${mat}' and Plant eq '${plt}'&$format=json`)
  ]);
  return { basic: basic.d, plant: plant_data.d, mrp3: mrp3.d, versions: pv.d.results };
}

fetchMM03(material, plant).then(d => console.log(JSON.stringify(d, null, 2))).catch(console.error);
