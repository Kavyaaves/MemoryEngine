// The type of drei's OrbitControls instance, shared by the scene and the camera director.
import type { ComponentRef } from "react";
import type { OrbitControls } from "@react-three/drei";

export type OrbitControlsHandle = ComponentRef<typeof OrbitControls>;
