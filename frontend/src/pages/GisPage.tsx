import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";

import { Alert, Checkbox, DataTable, EmptyState, ErrorState, LoadingState, PageHeader, Panel, SelectField } from "@/design-system";
import { toQuery } from "@/lib/api/client";
import { titleCase } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { options, useCategories } from "@/lib/reference";

interface Props { id: string; name: string; lgd_code: string | null; total: number; open: number; overdue: number }
interface Layer { type: "FeatureCollection"; features: Array<{ type: "Feature"; geometry: GeoJSON.Geometry; properties: Props }>; sources: Array<{ name: string; version: string; publisher: string }>; units_without_geometry: number; grievances_in_units_without_geometry: number }

const SCALE = ["#e3eaf4", "#a9bfdc", "#6b8fc2", "#2f5d9a", "#0b2e59"];
const FILTER_KEY: Record<string, string> = { district: "district_id", subdivision: "district_id", block: "block_id", gram_panchayat: "block_id", village: "village_id" };

function colour(value: number, max: number): string {
  if (value <= 0 || max <= 0) return "#ffffff";
  return SCALE[Math.min(SCALE.length - 1, Math.floor((value / max) * (SCALE.length - 1)))] ?? SCALE[0]!;
}

export function GisPage() {
  const config = useApi<{ tile_url: string | null; precise_allowed: boolean; levels: string[] }>("/gis/config");
  const cats = useCategories();
  const [level, setLevel] = useState("block");
  const [metric, setMetric] = useState<"open" | "overdue" | "total">("open");
  const [category, setCategory] = useState("");
  const [openOnly, setOpenOnly] = useState(false);
  const layer = useApi<Layer>(`/gis/layers/${level}`, { category_id: category || undefined, open_only: openOnly });
  const mapEl = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const geo = useRef<L.GeoJSON | null>(null);
  const max = useMemo(() => Math.max(0, ...(layer.data?.features.map((f) => f.properties[metric]) ?? [0])), [layer.data, metric]);

  useEffect(() => {
    if (!mapEl.current || map.current) return;
    map.current = L.map(mapEl.current, { attributionControl: true, zoomSnap: 0.25 });
    if (config.data?.tile_url) L.tileLayer(config.data.tile_url, { maxZoom: 18 }).addTo(map.current);
    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, [config.data?.tile_url]);

  useEffect(() => {
    const m = map.current;
    if (!m || !layer.data) return;
    geo.current?.remove();
    if (!layer.data.features.length) return;
    geo.current = L.geoJSON(layer.data as unknown as GeoJSON.FeatureCollection, {
      style: (f) => ({ color: "#1d2125", weight: 1, fillOpacity: 0.8, fillColor: colour((f?.properties as Props)[metric], max) }),
      pointToLayer: (f, latlng) => L.circleMarker(latlng, { radius: 6 + Math.min(14, (f.properties as Props)[metric]), color: "#1d2125", weight: 1, fillColor: colour((f.properties as Props)[metric], max), fillOpacity: 0.9 }),
      onEachFeature: (f, l) => {
        const p = f.properties as Props;
        l.bindTooltip(`${p.name}: ${p.open} open, ${p.overdue} overdue, ${p.total} total`);
      },
    }).addTo(m);
    m.fitBounds(geo.current.getBounds(), { padding: [12, 12] });
    m.attributionControl.setPrefix(false);
    for (const s of layer.data.sources) m.attributionControl.addAttribution(`Boundaries: ${s.name} (${s.publisher}, v${s.version})`);
  }, [layer.data, metric, max]);

  return (
    <>
      <PageHeader title="GIS maps" description="Grievances by administrative unit, drawn on registered boundary datasets only." />
      {config.data && !config.data.precise_allowed ? <Alert tone="info" title="Your role may view maps at block level and above." className="mb-4" /> : null}
      <div className="grid grid-cols-1 gap-x-4 md:grid-cols-4">
        <SelectField label="Administrative level" options={(config.data?.levels ?? ["block"]).map((l) => ({ value: l, label: titleCase(l) }))} placeholder="Block"
          value={level} onChange={(e) => setLevel(e.target.value || "block")} />
        <SelectField label="Shade by" options={[{ value: "open", label: "Open grievances" }, { value: "overdue", label: "Overdue grievances" }, { value: "total", label: "All grievances" }]} placeholder="Open grievances"
          value={metric} onChange={(e) => setMetric((e.target.value || "open") as typeof metric)} />
        <SelectField label="Category" options={options(cats.data?.filter((c) => !c.parent_id))} placeholder="All categories" value={category} onChange={(e) => setCategory(e.target.value)} />
        <div className="pt-7"><Checkbox label="Open grievances only" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /></div>
      </div>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[2fr_1fr]">
        <Panel title={`Map: ${titleCase(level)} level`} description={`Shading: ${metric} grievances (darker means more)`}>
          {layer.isError ? <ErrorState message="The map layer could not be loaded." /> : null}
          <div ref={mapEl} role="region" aria-label={`Map of grievances by ${level}. The same data is in the table.`} className="h-[28rem] w-full bg-surface-muted" />
          {layer.isLoading ? <LoadingState label="Loading map layer…" /> : null}
          {layer.data && !layer.data.features.length ? <EmptyState title="No boundaries are registered for this level">Import verified boundary data under Configuration.</EmptyState> : null}
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm" aria-hidden="true">
            Legend: {SCALE.map((c, i) => <span key={c} className="inline-flex items-center gap-1"><span className="inline-block h-3 w-5 border border-ink" style={{ background: c }} />{Math.round((i / (SCALE.length - 1)) * max)}</span>)}
          </div>
          {layer.data?.grievances_in_units_without_geometry ? (
            <p className="text-sm text-ink-muted">{layer.data.grievances_in_units_without_geometry} grievance(s) are in units without registered boundaries and are not drawn.</p>
          ) : null}
        </Panel>
        <Panel title="Units">
          <DataTable<Props> caption={`Grievances by ${level}`} rows={layer.data?.features.map((f) => f.properties).sort((a, b) => b[metric] - a[metric])}
            rowKey={(p) => p.id} loading={layer.isLoading} emptyTitle="No units"
            columns={[
              { key: "n", header: titleCase(level), render: (p) => <Link to={`/grievances${toQuery({ [FILTER_KEY[level] ?? "block_id"]: level === "district" || level === "subdivision" ? undefined : p.id, open_only: openOnly })}`}>{p.name}</Link> },
              { key: "o", header: "Open", align: "right", render: (p) => p.open },
              { key: "d", header: "Overdue", align: "right", render: (p) => p.overdue },
              { key: "t", header: "Total", align: "right", render: (p) => p.total },
            ]} />
        </Panel>
      </div>
    </>
  );
}
