import { SelectField } from "@/design-system";
import { options, useUnits } from "@/lib/reference";

export interface LocationValue {
  district_id?: string;
  block_id?: string;
  gram_panchayat_id?: string;
  village_id?: string;
  municipality_id?: string;
  ward_id?: string;
}

/** Cascading location selection from the official reference tables (no free coordinates). */
export function LocationPicker({ value, onChange, errors = {}, referenceBase = "/reference" }: {
  value: LocationValue;
  onChange: (v: LocationValue) => void;
  errors?: Record<string, string>;
  /** "/citizen/reference" on the citizen portal. */
  referenceBase?: string;
}) {
  const districts = useUnits("districts", undefined, true, referenceBase);
  const district = value.district_id ?? (districts.data?.length === 1 ? districts.data[0]?.id : undefined);
  const blocks = useUnits("blocks", district, Boolean(district), referenceBase);
  const gps = useUnits("gram_panchayats", value.block_id, Boolean(value.block_id), referenceBase);
  const villages = useUnits("villages", value.gram_panchayat_id, Boolean(value.gram_panchayat_id), referenceBase);
  const munis = useUnits("municipalities", district, Boolean(district), referenceBase);
  const wards = useUnits("wards", value.municipality_id, Boolean(value.municipality_id), referenceBase);
  return (
    <fieldset className="mb-2 border-0 p-0">
      <legend className="mb-2 font-semibold text-ink">Location</legend>
      <SelectField label="District" options={options(districts.data)} value={district ?? ""} onChange={(e) => onChange({ district_id: e.target.value || undefined })} />
      <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
        <SelectField label="Block" options={options(blocks.data)} value={value.block_id ?? ""} disabled={!district}
          onChange={(e) => onChange({ district_id: district, block_id: e.target.value || undefined })} error={errors["location.block_id"]} />
        <SelectField label="Gram panchayat" options={options(gps.data)} value={value.gram_panchayat_id ?? ""} disabled={!value.block_id}
          onChange={(e) => onChange({ ...value, district_id: district, gram_panchayat_id: e.target.value || undefined, village_id: undefined })} />
        <SelectField label="Village" options={options(villages.data)} value={value.village_id ?? ""} disabled={!value.gram_panchayat_id}
          onChange={(e) => onChange({ ...value, district_id: district, village_id: e.target.value || undefined })} />
      </div>
      <p className="mt-0 mb-2 text-sm text-ink-muted">For urban areas, choose the municipality and ward instead.</p>
      <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
        <SelectField label="Municipality" options={options(munis.data)} value={value.municipality_id ?? ""} disabled={!district}
          onChange={(e) => onChange({ district_id: district, municipality_id: e.target.value || undefined })} />
        <SelectField label="Ward" options={options(wards.data)} value={value.ward_id ?? ""} disabled={!value.municipality_id}
          onChange={(e) => onChange({ ...value, district_id: district, ward_id: e.target.value || undefined })} />
      </div>
    </fieldset>
  );
}
