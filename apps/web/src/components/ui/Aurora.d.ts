import type { CSSProperties, JSX } from "react";

/** Tipos do Aurora (React Bits, WebGL2 puro, sem dependencias). Aurora.jsx e o original, com dois ajustes: um comentario de eslint no settingsRef e sem loseContext na limpeza (quebrava no StrictMode). */
export interface AuroraProps {
  colorStops?: string[];
  amplitude?: number;
  blend?: number;
  speed?: number;
  time?: number;
  height?: number;
  scale?: number;
  glow?: number;
  brightness?: number;
  layers?: number;
  direction?: "top" | "bottom";
  mouseInteraction?: boolean;
  intro?: boolean;
  opacity?: number;
  /** Para fundo branco. */
  lightMode?: boolean;
  paused?: boolean;
  dpr?: number;
  className?: string;
  style?: CSSProperties;
}

declare const Aurora: (props: AuroraProps) => JSX.Element;
export default Aurora;
