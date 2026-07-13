import { useEffect, useState } from "react";

export type DensityPreference = "comfortable" | "compact";

const DENSITY_KEY = "pla-density";

export function readDensityPreference(): DensityPreference {
  return localStorage.getItem(DENSITY_KEY) === "compact"
    ? "compact"
    : "comfortable";
}

export function useDensityPreference(): [
  DensityPreference,
  (density: DensityPreference) => void,
] {
  const [density, setDensityState] = useState(readDensityPreference);
  const setDensity = (value: DensityPreference) => {
    localStorage.setItem(DENSITY_KEY, value);
    setDensityState(value);
  };
  useEffect(() => {
    document.documentElement.dataset.density = density;
  }, [density]);
  return [density, setDensity];
}
