import { useApi } from "@/lib/hooks";

export interface Source { id: string; code: string; name_en: string; channel_type: string; integration_mode: string; is_active: boolean; description: string | null; name_local: string | null }
export interface Department { id: string; code: string; name_en: string; name_local: string | null; parent_id: string | null; is_active: boolean; description: string | null }
export interface Category { id: string; code: string; name_en: string; name_local: string | null; parent_id: string | null; default_department_id: string | null; is_essential_service: boolean; is_active: boolean; description: string | null }
export interface Unit { id: string; name_en: string; lgd_code: string | null; is_active: boolean; has_geometry: boolean; [k: string]: unknown }

export function useSources() {
  return useApi<Source[]>("/reference/sources");
}
export function useDepartments() {
  return useApi<Department[]>("/reference/departments");
}
export function useCategories() {
  return useApi<Category[]>("/reference/categories");
}
export function useUnits(level: string, parentId?: string | null, enabled = true, base = "/reference") {
  return useApi<Unit[]>(enabled ? `${base}/units/${level}` : null, parentId ? { parent_id: parentId } : undefined);
}

export function options<T extends { id: string; name_en: string; is_active?: boolean }>(rows: T[] | undefined) {
  return (rows ?? []).filter((r) => r.is_active !== false).map((r) => ({ value: r.id, label: r.name_en }));
}
