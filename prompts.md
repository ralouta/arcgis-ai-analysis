## Arcade – Canopy Width (diameter from circle polygon)

**Prompt for Arcade Assistant / Field Maps Calculate:**

> Use Length to get the polygon perimeter in meters, divide by PI to get the diameter, round to 2 decimal places.

**Expected expression:**

```arcade
Round(LengthGeodetic($feature, 'meters') / PI, 2)
```

**Notes:**
- `Length()` doesn't accept a unit param — use `LengthGeodetic()` instead
- Layer is WGS84 (angular); `LengthGeodetic` handles the geodesic conversion
- Assign to `canopy_width_m` field as a Calculation attribute rule (Insert + Update)

---

## Arcade – Observer (logged-in user full name)

**Prompt for Arcade Assistant / Field Maps Calculate:**

> Use feature functions to get the current user and calculate their full name.

**Expected expression:**

```arcade
GetUser(Portal()).fullName
```

**Notes:**
- `GetUser(Portal())` returns the portal user object; `.fullName` gives "First Last"
- Assign to `observer` field as a Calculation attribute rule (Insert)

