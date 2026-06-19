// Karrada AOI [west, south, east, north]
export const KARRADA_BBOX: [number, number, number, number] = [
  44.385, 33.285, 44.43, 33.32,
];

export const KARRADA_CENTER: [number, number] = [
  (KARRADA_BBOX[0] + KARRADA_BBOX[2]) / 2,
  (KARRADA_BBOX[1] + KARRADA_BBOX[3]) / 2,
];
