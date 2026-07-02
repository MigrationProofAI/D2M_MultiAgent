## Lessons Learned from Bicycle BOM Genesis (Session 2026-06)

### Lesson 1: extend_to_plant defaults to MRPType=ND
- **Impact:** All sub-BOM materials (HALBs + HAWAs) had MRP switched off silently
- **Detection:** MRP ran on FERT only; no planned orders or purchase reqs for components
- **Fix:** Use enable_plant_production (not extend_to_plant or update_material) to set PD+controller

### Lesson 2: update_material patches A_Product (header), not A_ProductPlant
- **Impact:** Cannot set MRPType or MRPResponsible via update_material
- **Error:** '400 Property MRPResponsible is invalid'
- **Fix:** Use enable_plant_production which PATCHes A_ProductPlant correctly

### Lesson 3: MRPType=PD requires MRPResponsible — they are a pair
- **Impact:** Setting PD without a controller causes SAP error M3/069
- **Valid controllers for plant 1710:** 001, 002, MZ3
- **Fix:** Always pass both mrp_type=PD AND mrp_controller=001 together

### Lesson 4: extend_to_plant does not accept mrp_controller parameter
- **Impact:** Cannot use extend_to_plant to set PD+controller in a single call
- **Error:** 'TypeError: extend_to_plant() got an unexpected keyword argument mrp_controller'
- **Fix:** Use enable_plant_production instead
