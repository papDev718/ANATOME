import { useEffect, useLayoutEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

import "../css/Canvas3D.css";
import { displayAnatomyName } from "../utils/anatomyName";
import { areaAt, areaGroupKey, areaLabel, areaOf, sideOf } from "../utils/bodyAreas";

gsap.registerPlugin(ScrollTrigger);

// Each selectable structure in this Blender export is an individually named GLB mesh.
// Keep its original object name when re-exporting so selection and saved pain spots still map correctly.
const MODEL_URL = "/models/zanatomy_split.glb";
const SELECTED_COLOR = new THREE.Color("#ff5b3a");
const HOVER_COLOR = new THREE.Color("#f3e6cf");
const SUGGESTED_COLOR = new THREE.Color("#e3a14f");
const MUSCLE_COLOR = new THREE.Color("#a64a50");
const CONNECTIVE_COLOR = new THREE.Color("#cbb6a2");
const CONNECTIVE_NAME = /fascia|ligament|tendon|retinaculum|bursa|sheath|aponeurosis|septum|band|capsule/i;

const ANATOMY_LIBRARY = {
  deltoid: {
    scientificName: "Musculus deltoideus",
    summary: "The deltoid forms the shoulder contour and helps lift, rotate, and stabilize the arm.",
    causes: ["Repetitive overhead loading", "Rapid increases in training volume", "Direct impact or muscular strain"],
    rehab: ["Pain-free pendulum movements", "Gentle isometric shoulder abduction", "Progressive external-rotation strengthening"],
  },
  biceps: {
    scientificName: "Musculus biceps brachii",
    summary: "The biceps crosses the shoulder and elbow, helping flex the elbow and rotate the forearm.",
    causes: ["Repeated lifting or pulling", "High-volume elbow flexion", "Sudden eccentric loading"],
    rehab: ["Gentle elbow range of motion", "Submaximal isometric curls", "Slow, progressive resistance work"],
  },
  triceps: {
    scientificName: "Musculus triceps brachii",
    summary: "The triceps is the primary elbow extensor and assists shoulder stability during pushing activity.",
    causes: ["Repeated pushing movements", "Heavy overhead extension", "Direct strain near the elbow attachment"],
    rehab: ["Comfortable elbow flexion and extension", "Low-load extension isometrics", "Progressive pressing tolerance"],
  },
  pectoralis: {
    scientificName: "Musculus pectoralis major",
    summary: "The pectoralis major moves the arm across the body and contributes to pressing and shoulder control.",
    causes: ["Heavy pressing or fly movements", "Forceful arm extension", "Sudden load at a stretched position"],
    rehab: ["Comfortable chest and shoulder mobility", "Gentle wall-based isometrics", "Gradual return to horizontal pressing"],
  },
  quadriceps: {
    scientificName: "Musculus quadriceps femoris",
    summary: "The quadriceps straightens the knee and controls load during walking, stairs, squatting, and landing.",
    causes: ["Sprinting or jumping load", "Rapid increases in squat volume", "Direct impact to the thigh"],
    rehab: ["Pain-free knee range of motion", "Quadriceps isometric holds", "Progressive squat and step loading"],
  },
  hamstring: {
    scientificName: "Hamstring muscle group",
    summary: "The hamstrings bend the knee, extend the hip, and control the leg during high-speed movement.",
    causes: ["High-speed running exposure", "Forceful hip flexion with knee extension", "Sudden acceleration or deceleration"],
    rehab: ["Comfortable hip and knee movement", "Submaximal bridge isometrics", "Progressive eccentric hamstring loading"],
  },
  patellar: {
    scientificName: "Ligamentum patellae",
    summary: "The patellar ligament connects the kneecap to the shin and transfers quadriceps force at the knee.",
    causes: ["Repeated jumping or landing", "Rapid changes in running load", "High-volume deep knee flexion"],
    rehab: ["Comfortable knee-extension isometrics", "Slow progressive squat loading", "Graded return to jumping volume"],
  },
  achilles: {
    scientificName: "Tendo calcaneus",
    summary: "The Achilles tendon connects the calf muscles to the heel and transfers force during walking and running.",
    causes: ["Rapid increases in running volume", "Repeated jumping", "Sudden high-force acceleration"],
    rehab: ["Comfortable ankle motion", "Calf isometric holds", "Progressive heel-raise loading"],
  },
};

const DEFAULTS = {
  skeletal: {
    scientificName: "Skeletal structure",
    summary: "This bone forms part of the body's supporting framework and provides protection or attachment for surrounding tissues.",
    causes: ["Direct impact", "Repetitive local loading", "Stress transferred from a nearby joint"],
    rehab: ["Protect painful movement initially", "Restore comfortable range gradually", "Seek assessment for persistent focal bone pain"],
  },
  muscular: {
    scientificName: "Skeletal muscle",
    summary: "This muscle contributes to movement, posture, and load control in its surrounding region.",
    causes: ["Repetitive or unfamiliar loading", "Sudden changes in activity volume", "Direct strain or impact"],
    rehab: ["Keep movement within a comfortable range", "Use gradual symptom-guided loading", "Seek guidance when symptoms persist"],
  },
  connective: {
    scientificName: "Connective-tissue structure",
    summary: "This structure helps connect, support, or stabilize nearby bones and muscles.",
    causes: ["Repeated tensile loading", "Joint stress or sudden force", "Rapid changes in activity volume"],
    rehab: ["Reduce aggravating load temporarily", "Maintain comfortable joint motion", "Progress resistance gradually"],
  },
};

function canonicalName(name = "") {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function anatomyForPart(part) {
  const name = canonicalName(part?.name);
  if (/biceps femoris|semitendinosus|semimembranosus/.test(name)) return ANATOMY_LIBRARY.hamstring;
  const match = Object.keys(ANATOMY_LIBRARY).find((key) => name.includes(key));
  return match ? ANATOMY_LIBRARY[match] : DEFAULTS[part?.system] || DEFAULTS.muscular;
}

// Broad fascia sheets wrap whole regions; in the body-area layer they would
// hide the muscles and tendons a patient recognises.
const SHEET_NAME = /fascia(?!e latae)|aponeurosis|septum/i;

function layerAllows(mode, part) {
  if (mode === "area") return !part.isSheet;
  return part.system === mode;
}

const LAYERS = [["area", "Body areas"], ["muscular", "Muscles"], ["connective", "Connective tissue"]];


// A target is what the patient pointed at: one structure (Muscles /
// Connective layers) or one everyday area (Body areas layer). Pointing only
// proposes a spot; App records it when the patient presses Save.
function targetForPart(part, layer, point) {
  const clickPosition = point ? `${point.x} ${point.y} ${point.z}` : null;
  if (layer === "area" && part.area) {
    const area = areaAt(part.name, point) || part.area;
    return {
      mode: "area",
      key: areaGroupKey(area, part.side),
      regionName: areaLabel(area, part.side),
      areaKey: area,
      areaLabel: areaLabel(area, part.side),
      side: part.side,
      system: "area",
      clickPosition,
    };
  }
  return { mode: "structure", key: part.name, regionName: part.name, system: part.system, clickPosition };
}

export default function BodyPartsCanvas({ activeTarget, painData = {}, onPick, onDismiss, frameBodyRef, pickAreaRef, suggestedKeys = [] }) {
  const stageRef = useRef(null);
  const hostRef = useRef(null);
  const tooltipRef = useRef(null);
  const blurRef = useRef(null);
  const infoPanelRef = useRef(null);
  const engineRef = useRef(null);
  const painDataRef = useRef(painData);
  const selectedRef = useRef(null); // { key, parts: Set, center, bounds, name }
  const hoveredKeyRef = useRef(null);
  const focusRef = useRef(() => {});
  const layerRef = useRef("area");
  const onPickRef = useRef(onPick);
  const onDismissRef = useRef(onDismiss);
  const activeKeyRef = useRef(activeTarget?.key || null);

  const [modelStatus, setModelStatus] = useState("loading");
  const [loadProgress, setLoadProgress] = useState(0);
  const [loadError, setLoadError] = useState("");
  const [layerMode, setLayerMode] = useState("area");
  const [selection, setSelection] = useState(null);
  const [pickerOptions, setPickerOptions] = useState([]);

  useEffect(() => { onPickRef.current = onPick; onDismissRef.current = onDismiss; });
  useEffect(() => { activeKeyRef.current = activeTarget?.key || null; }, [activeTarget]);

  const prevPainCountRef = useRef(Object.keys(painData).length);
  useEffect(() => {
    const prev = prevPainCountRef.current;
    const next = Object.keys(painData).length;
    prevPainCountRef.current = next;
    painDataRef.current = painData;
    engineRef.current?.refreshVisuals();
    if (next === 0 && prev > 0 && !activeKeyRef.current) engineRef.current?.frameBody();
  }, [painData]);

  useEffect(() => {
    if (frameBodyRef) frameBodyRef.current = () => engineRef.current?.frameBody();
  }, [frameBodyRef]);

  useEffect(() => {
    if (!pickAreaRef) return;
    pickAreaRef.current = (key) => {
      const target = engineRef.current?.targetFor(key);
      if (target) onPickRef.current?.(target);
    };
  }, [pickAreaRef]);

  const suggestedRef = useRef(new Set());
  const suggestedSignature = suggestedKeys.join("|");
  useEffect(() => {
    suggestedRef.current = new Set(suggestedSignature ? suggestedSignature.split("|") : []);
    engineRef.current?.refreshVisuals();
  }, [suggestedSignature]);

  // Follow the active target chosen in App (a click, the picker, or Edit in the list).
  useEffect(() => {
    const engine = engineRef.current;
    if (!engine?.ready) return;
    if (!activeTarget) {
      if (selectedRef.current) {
        selectedRef.current = null;
        setSelection(null);
        engine.refreshVisuals();
        engine.frameBody();
      }
      return;
    }
    const wanted = activeTarget.mode === "area" ? "area" : activeTarget.system === "connective" ? "connective" : "muscular";
    if (layerRef.current !== wanted) {
      layerRef.current = wanted;
      setLayerMode(wanted);
      engine.updatePicker();
    }
    if (selectedRef.current?.key !== activeTarget.key) engine.select(activeTarget.key);
  }, [activeTarget, modelStatus]);

  useEffect(() => {
    const host = hostRef.current;
    const stage = stageRef.current;
    if (!host || !stage) return undefined;

    let disposed = false;
    let frame = 0;
    let resizeFrame = 0;
    let pointerDown = null;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b0b0a);
    scene.fog = new THREE.Fog(0x0b0b0a, 4.6, 10);

    const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 50);
    camera.position.set(0.55, 0.95, 4.2);
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance", preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.92;
    renderer.domElement.setAttribute("aria-label", "Interactive adult human musculoskeletal anatomy");
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = false;
    controls.minDistance = 0.25;
    controls.maxDistance = 8;
    controls.target.set(0, 0.9, 0);

    scene.add(new THREE.HemisphereLight(0xf4efe6, 0x1a1210, 1.1));
    const key = new THREE.DirectionalLight(0xfff4e8, 2.2);
    key.position.set(-2.8, 4.5, 4);
    scene.add(key);
    const fill = new THREE.PointLight(0xc9d4e0, 5, 9, 2);
    fill.position.set(3, 1.5, 2.4);
    scene.add(fill);
    const rim = new THREE.DirectionalLight(0xff6b78, 1.2);
    rim.position.set(2.4, 2.4, -3);
    scene.add(rim);

    const platform = new THREE.Mesh(
      new THREE.CylinderGeometry(0.67, 0.72, 0.035, 96),
      new THREE.MeshStandardMaterial({ color: 0x1a1917, roughness: 0.8, metalness: 0.1 }),
    );
    platform.position.y = -0.025;
    scene.add(platform);

    const root = new THREE.Group();
    scene.add(root);
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const parts = [];
    const pickableMeshes = [];
    const partByMesh = new Map();
    const groups = new Map(); // area group key -> { key, label, area, parts, bounds, center }

    const resize = () => {
      cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(() => {
        const width = Math.max(host.clientWidth, 1);
        const height = Math.max(host.clientHeight, 1);
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
      });
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();

    const animateCamera = (position, target, duration = 0.8) => {
      gsap.killTweensOf(camera.position);
      gsap.killTweensOf(controls.target);
      if (reduceMotion.matches) {
        camera.position.copy(position);
        controls.target.copy(target);
        controls.update();
        return;
      }
      gsap.to(camera.position, { ...position, duration, ease: "expo.out", overwrite: true, onUpdate: () => controls.update() });
      gsap.to(controls.target, { ...target, duration, ease: "expo.out", overwrite: true });
    };

    const frameBody = () => {
      const box = new THREE.Box3().setFromObject(root);
      if (box.isEmpty()) return;
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const target = center.clone().add(new THREE.Vector3(0, -0.11, 0));
      const distance = Math.max(size.y * 1.72, 3.8);
      animateCamera(target.clone().add(new THREE.Vector3(0.16, 0.04, 1).normalize().multiplyScalar(distance)), target, 1);
    };

    const focusOn = (item, view = 0) => {
      if (!item) return;
      const center = item.center;
      const size = item.bounds.getSize(new THREE.Vector3());
      const vertical = THREE.MathUtils.degToRad(camera.fov);
      const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * camera.aspect);
      const fitDistance = Math.max(
        size.y / (2 * Math.tan(vertical / 2)),
        size.x / (2 * Math.tan(horizontal / 2)),
        size.z * 1.6,
      );
      // Leave a narrow anatomical margin around the selected structure.
      const distance = Math.max(fitDistance * (view === 2 ? 1.15 : 1.32), 0.42);
      const direction = camera.position.clone().sub(controls.target).normalize();
      const bodyCenter = new THREE.Box3().setFromObject(root).getCenter(new THREE.Vector3());
      const outward = center.clone().sub(bodyCenter);
      outward.set(outward.x * 0.9, 0.06, outward.z * 2.5);
      if (outward.lengthSq() > 0.002 && direction.dot(outward.normalize()) < 0.25) direction.copy(outward);
      if (view === 1) direction.applyAxisAngle(new THREE.Vector3(0, 1, 0), 0.28);
      if (view === 2) direction.applyAxisAngle(new THREE.Vector3(0, 1, 0), -0.32);
      animateCamera(center.clone().add(direction.multiplyScalar(distance)), center, 0.95);
    };
    focusRef.current = (view) => focusOn(selectedRef.current, view);

    const keyForHit = (part, point) => {
      if (layerRef.current !== "area") return part.name;
      return areaGroupKey(areaAt(part.name, point) || part.area, part.side);
    };
    const hoveredPartRef = { current: null };

    const refreshVisuals = () => {
      const selected = selectedRef.current;
      const hoveredKey = hoveredKeyRef.current;
      const spots = Object.values(painDataRef.current);
      const savedByName = new Map(spots.filter((s) => s.mode !== "area").map((spot) => [canonicalName(spot.regionName), spot]));
      const savedByArea = new Map(spots.filter((s) => s.mode === "area").map((spot) => [areaGroupKey(spot.areaKey, spot.side), spot]));
      parts.forEach((part) => {
        const isSelected = Boolean(selected?.parts.has(part));
        const partKey = layerRef.current === "area" ? part.groupKey : part.name;
        const isHovered = !isSelected && hoveredKey !== null && (partKey === hoveredKey || part === hoveredPartRef.current);
        const isVisible = layerAllows(layerRef.current, part) || isSelected;
        const spot = savedByName.get(canonicalName(part.name)) || savedByArea.get(part.groupKey);
        const dimmed = Boolean(selected && !isSelected);
        part.meshes.forEach((mesh) => { mesh.visible = isVisible; });
        part.materials.forEach((material, index) => {
          if (material.color) {
            material.color.copy(part.baseColors[index]);
            if (spot) material.color.lerp(SELECTED_COLOR, Math.min((spot.severity || 5) / 12, 0.7));
            else if (layerRef.current === "area" && !selected && suggestedRef.current.has(part.groupKey)) material.color.lerp(SUGGESTED_COLOR, 0.45);
            if (isHovered) material.color.lerp(HOVER_COLOR, 0.72);
            if (isSelected) material.color.lerp(SELECTED_COLOR, 0.92);
          }
          if (material.emissive) {
            material.emissive.copy(part.baseEmissives[index]);
            if (isHovered) material.emissive.lerp(HOVER_COLOR, 0.28);
            if (isSelected) material.emissive.lerp(SELECTED_COLOR, 0.3);
          }
          const transparent = dimmed || part.baseTransparent[index];
          if (material.transparent !== transparent) {
            material.transparent = transparent;
            material.needsUpdate = true;
          }
          material.depthWrite = dimmed ? false : part.baseDepthWrite[index];
          material.opacity = part.baseOpacity[index] * (dimmed ? 0.36 : 1);
        });
      });
    };

    const updatePicker = () => {
      if (layerRef.current === "area") {
        setPickerOptions([...groups.values()].map((g) => ({ key: g.key, label: g.label })).sort((a, b) => a.label.localeCompare(b.label)));
      } else {
        setPickerOptions(parts.filter((part) => layerAllows(layerRef.current, part))
          .map((part) => ({ key: part.name, label: displayAnatomyName(part.name) }))
          .sort((a, b) => a.label.localeCompare(b.label)));
      }
    };

    const selectionFor = (targetKey) => {
      const group = groups.get(targetKey);
      if (group) return { key: targetKey, name: group.label, area: group.area, parts: new Set(group.parts), center: group.center, bounds: group.bounds, count: group.parts.length };
      const part = parts.find((candidate) => canonicalName(candidate.name) === canonicalName(targetKey));
      if (!part) return null;
      return { key: targetKey, name: part.name, system: part.system, part, parts: new Set([part]), center: part.center, bounds: part.bounds };
    };

    const select = (targetKey) => {
      const next = selectionFor(targetKey);
      if (!next) return;
      selectedRef.current = next;
      hoveredKeyRef.current = null;
      setSelection(next);
      refreshVisuals();
      requestAnimationFrame(() => focusOn(next));
    };

    const engine = {
      parts,
      camera,
      controls,
      root,
      ready: false,
      frameBody,
      refreshVisuals,
      updatePicker,
      select,
      targetFor(targetKey) {
        const group = groups.get(targetKey);
        if (group) return targetForPart(group.parts[0], "area", null);
        const part = parts.find((candidate) => candidate.name === targetKey);
        return part ? targetForPart(part, layerRef.current, null) : null;
      },
      setLayer(mode) {
        layerRef.current = mode;
        hoveredKeyRef.current = null;
        refreshVisuals();
        updatePicker();
      },
    };
    engineRef.current = engine;

    const loadModel = async () => {
      try {
        const gltf = await new GLTFLoader().loadAsync(MODEL_URL, (event) => {
          if (event.lengthComputable && !disposed) setLoadProgress(Math.round((event.loaded / event.total) * 100));
        });
        if (disposed) return;
        root.add(gltf.scene);
        root.updateMatrixWorld(true);
        gltf.scene.children.forEach((node) => {
          const meshes = [];
          const materials = [];
          node.traverse((mesh) => {
            if (!mesh.isMesh || !mesh.geometry) return;
            const sourceMaterials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
            const meshMaterials = sourceMaterials.map((material) => material.clone());
            mesh.material = Array.isArray(mesh.material) ? meshMaterials : meshMaterials[0];
            meshes.push(mesh);
            materials.push(...meshMaterials);
          });
          if (meshes.length === 0) return;
          // GLTFLoader can split one Blender object into multiple primitive meshes.
          // The original Blender name is retained on the parent node's userData.
          const name = node.userData.name || node.name || `Anatomical structure ${parts.length + 1}`;
          const system = CONNECTIVE_NAME.test(name) ? "connective" : "muscular";
          const color = system === "connective" ? CONNECTIVE_COLOR : MUSCLE_COLOR;
          const variation = 0.9 + ((parts.length * 37) % 17) / 100;
          materials.forEach((material) => {
            if (material.color) material.color.copy(color).multiplyScalar(variation);
            if (material.emissive) material.emissive.set(0x000000);
            if ("metalness" in material) material.metalness = 0.02;
            if ("roughness" in material) material.roughness = 0.63;
          });
          const bounds = new THREE.Box3().setFromObject(node);
          if (bounds.isEmpty()) return;
          const side = sideOf(name);
          const area = areaOf(name);
          const part = {
            id: node.uuid,
            name,
            system,
            side,
            area,
            groupKey: area ? areaGroupKey(area, side) : name,
            isSheet: SHEET_NAME.test(name),
            meshes,
            materials,
            baseColors: materials.map((material) => material.color?.clone() || null),
            baseEmissives: materials.map((material) => material.emissive?.clone() || null),
            baseOpacity: materials.map((material) => material.opacity),
            baseTransparent: materials.map((material) => material.transparent),
            baseDepthWrite: materials.map((material) => material.depthWrite),
            bounds,
            center: bounds.getCenter(new THREE.Vector3()),
          };
          parts.push(part);
          meshes.forEach((mesh) => {
            pickableMeshes.push(mesh);
            partByMesh.set(mesh, part);
          });
          if (area) {
            if (!groups.has(part.groupKey)) {
              groups.set(part.groupKey, { key: part.groupKey, label: areaLabel(area, side), area, parts: [], bounds: new THREE.Box3() });
            }
            const group = groups.get(part.groupKey);
            group.parts.push(part);
            // Fascia sheets reach far beyond the area; frame on what is visible.
            if (!part.isSheet) group.bounds.union(bounds);
          }
        });
        if (parts.length === 0) throw new Error("This GLB contains no selectable anatomy meshes.");
        groups.forEach((group) => {
          if (group.bounds.isEmpty()) group.parts.forEach((part) => group.bounds.union(part.bounds));
          group.center = group.bounds.getCenter(new THREE.Vector3());
        });
        engine.ready = true;
        refreshVisuals();
        updatePicker();
        frameBody();
        setLoadProgress(100);
        setModelStatus("ready");
      } catch (error) {
        if (disposed) return;
        setLoadError(error instanceof Error ? error.message : "The anatomy model could not be loaded.");
        setModelStatus("error");
      }
    };
    loadModel();

    const updatePointer = (event) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    };

    const hitTest = (event) => {
      updatePointer(event);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(pickableMeshes.filter((mesh) => mesh.visible), false)[0];
      return hit ? { ...hit, part: partByMesh.get(hit.object) } : null;
    };

    const hideTooltip = () => {
      if (!tooltipRef.current) return;
      tooltipRef.current.style.opacity = "0";
      tooltipRef.current.style.transform = "translate3d(0, 4px, 0)";
    };

    const onMove = (event) => {
      if (event.buttons) return hideTooltip();
      const hit = hitTest(event);
      const next = hit?.part || null;
      const nextKey = next ? keyForHit(next, hit.point) : null;
      if (nextKey !== hoveredKeyRef.current || next !== hoveredPartRef.current) {
        hoveredKeyRef.current = nextKey;
        hoveredPartRef.current = next;
        refreshVisuals();
        renderer.domElement.style.cursor = next ? "pointer" : "grab";
      }
      if (!next || !tooltipRef.current) return hideTooltip();
      const rect = stage.getBoundingClientRect();
      tooltipRef.current.textContent = layerRef.current === "area" && next.area ? areaLabel(areaAt(next.name, hit.point) || next.area, next.side) : displayAnatomyName(next.name);
      tooltipRef.current.style.left = `${event.clientX - rect.left + 16}px`;
      tooltipRef.current.style.top = `${event.clientY - rect.top + 16}px`;
      tooltipRef.current.style.opacity = "1";
      tooltipRef.current.style.transform = "translate3d(0, 0, 0)";
    };

    const onClick = (event) => {
      if (pointerDown && Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) > 5) return;
      const hit = hitTest(event);
      if (hit?.part) {
        // A tap inside the open area marks the exact spot; empty space,
        // Escape or Close dismiss it.
        onPickRef.current?.(targetForPart(hit.part, layerRef.current, hit.point));
      } else if (selectedRef.current) {
        onDismissRef.current?.();
      }
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape" && selectedRef.current) onDismissRef.current?.();
    };
    const onDown = (event) => { pointerDown = { x: event.clientX, y: event.clientY }; };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", hideTooltip);
    renderer.domElement.addEventListener("click", onClick);
    window.addEventListener("keydown", onKeyDown);

    const projectedCorner = new THREE.Vector3();
    const projectedCenter = new THREE.Vector3();
    const render = () => {
      controls.update();
      const selected = selectedRef.current;
      const blur = blurRef.current;
      if (selected && blur) {
        camera.updateMatrixWorld();
        const { min, max } = selected.bounds;
        const width = Math.max(host.clientWidth, 1);
        const height = Math.max(host.clientHeight, 1);
        let left = Infinity;
        let right = -Infinity;
        let top = Infinity;
        let bottom = -Infinity;
        for (let corner = 0; corner < 8; corner += 1) {
          const x = corner & 1 ? max.x : min.x;
          const y = corner & 2 ? max.y : min.y;
          const z = corner & 4 ? max.z : min.z;
          projectedCorner.set(x, y, z).project(camera);
          const px = (projectedCorner.x + 1) * width / 2;
          const py = (1 - projectedCorner.y) * height / 2;
          left = Math.min(left, px);
          right = Math.max(right, px);
          top = Math.min(top, py);
          bottom = Math.max(bottom, py);
        }
        projectedCenter.copy(selected.center).project(camera);
        blur.style.setProperty("--focus-x", `${(projectedCenter.x + 1) * width / 2}px`);
        blur.style.setProperty("--focus-y", `${(1 - projectedCenter.y) * height / 2}px`);
        blur.style.setProperty("--focus-rx", `${Math.min(width * 0.42, Math.max(110, (right - left) * 0.58 + 24))}px`);
        blur.style.setProperty("--focus-ry", `${Math.min(height * 0.46, Math.max(100, (bottom - top) * 0.58 + 24))}px`);
      }
      renderer.render(scene, camera);
      frame = requestAnimationFrame(render);
    };
    render();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      cancelAnimationFrame(resizeFrame);
      observer.disconnect();
      window.removeEventListener("keydown", onKeyDown);
      controls.dispose();
      gsap.killTweensOf(camera.position);
      gsap.killTweensOf(controls.target);
      const geometries = new Set();
      const materials = new Set();
      root.traverse((object) => {
        if (object.geometry) geometries.add(object.geometry);
        if (object.material) (Array.isArray(object.material) ? object.material : [object.material]).forEach((material) => materials.add(material));
      });
      geometries.forEach((geometry) => geometry.dispose());
      materials.forEach((material) => material.dispose());
      platform.geometry.dispose();
      platform.material.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      engineRef.current = null;
    };
  }, []);

  const panelOpen = Boolean(selection);
  const selectedAnatomy = selection?.part ? anatomyForPart(selection.part) : null;

  useLayoutEffect(() => {
    if (!panelOpen || !infoPanelRef.current || !selectedAnatomy) return undefined;
    const context = gsap.context(() => {
      gsap.utils.toArray(".anatomy-info__section").forEach((section, index) => {
        if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) gsap.fromTo(section, { opacity: 0.4, y: 12, clipPath: "inset(0 0 10% 0)" }, {
          opacity: 1,
          y: 0,
          clipPath: "inset(0 0 0% 0)",
          duration: 0.28,
          ease: "power3.out",
          scrollTrigger: { trigger: section, scroller: infoPanelRef.current, start: "top 82%", toggleActions: "play none none reverse" },
        });
        ScrollTrigger.create({
          trigger: section,
          scroller: infoPanelRef.current,
          start: "top 56%",
          end: "bottom 38%",
          onEnter: () => focusRef.current(index),
          onEnterBack: () => focusRef.current(index),
        });
      });
    }, infoPanelRef);
    requestAnimationFrame(() => ScrollTrigger.refresh());
    return () => context.revert();
  }, [panelOpen, selection, selectedAnatomy]);

  const changeLayer = (mode) => {
    if (mode === layerMode) return;
    setLayerMode(mode);
    engineRef.current?.setLayer(mode);
    // A proposal made in another layer no longer matches what is on screen.
    if (activeKeyRef.current) onDismissRef.current?.();
  };

  const setView = (view) => {
    const engine = engineRef.current;
    if (!engine?.root) return;
    const box = new THREE.Box3().setFromObject(engine.root);
    const center = box.getCenter(new THREE.Vector3()).add(new THREE.Vector3(0, -0.11, 0));
    const size = box.getSize(new THREE.Vector3());
    const direction = {
      front: new THREE.Vector3(0, 0.03, 1),
      back: new THREE.Vector3(0, 0.03, -1),
      left: new THREE.Vector3(-1, 0.03, 0),
      right: new THREE.Vector3(1, 0.03, 0),
    }[view];
    const position = center.clone().add(direction.normalize().multiplyScalar(Math.max(size.y * 1.72, 3.8)));
    gsap.to(engine.camera.position, { ...position, duration: 0.75, ease: "expo.out", overwrite: true });
    gsap.to(engine.controls.target, { ...center, duration: 0.75, ease: "expo.out", overwrite: true });
  };

  const handlePickerChange = (event) => {
    const target = engineRef.current?.targetFor(event.target.value);
    if (target) onPickRef.current?.(target);
  };

  const areaHint = layerMode === "area" ? "Tap where it hurts." : "Tap a muscle or tissue.";

  return (
    <main ref={stageRef} className={`anatomy-explorer ${panelOpen ? "anatomy-explorer--split" : ""}`}>
      <section className="anatomy-stage" aria-label="3D anatomy pain selector">
        <div ref={hostRef} className="anatomy-stage__canvas" />
        <div ref={blurRef} className={`anatomy-stage__focus-blur ${panelOpen ? "is-active" : ""}`} aria-hidden="true" />

        <div className="anatomy-stage__topline">
          <div className={`anatomy-stage__status ${modelStatus === "error" ? "is-error" : ""} ${modelStatus === "ready" ? "is-hidden" : ""}`} aria-live="polite">
            <span className="anatomy-stage__status-dot" aria-hidden="true" />
            {modelStatus === "loading" && `Loading the body · ${loadProgress}%`}
            {modelStatus === "error" && "Anatomy unavailable"}
          </div>

          <label className="anatomy-stage__region-picker">
            <span>{layerMode === "area" ? "Can't find it? Pick from a list" : "Or choose a structure"}</span>
            <select value={activeTarget?.key && pickerOptions.some((o) => o.key === activeTarget.key) ? activeTarget.key : ""} onChange={handlePickerChange} disabled={modelStatus !== "ready"}>
              <option value="">{layerMode === "area" ? "Choose an area" : "Choose a structure"}</option>
              {pickerOptions.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}
            </select>
          </label>
        </div>

        <div className="anatomy-stage__layer-controls" role="group" aria-label="What to point at">
          {LAYERS.map(([mode, label]) => (
            <button key={mode} type="button" className={layerMode === mode ? "is-active" : ""} aria-pressed={layerMode === mode} onClick={() => changeLayer(mode)}>{label}</button>
          ))}
        </div>

        <div className="anatomy-stage__view-controls" aria-label="Model camera views">
          {[['front', 'Front'], ['back', 'Back'], ['left', 'Left'], ['right', 'Right']].map(([view, label]) => (
            <button key={view} type="button" onClick={() => setView(view)}>{label}</button>
          ))}
        </div>

        <p className="anatomy-stage__hint">{areaHint} Drag to turn the body, scroll to zoom.</p>
        {modelStatus === "error" && <p className="anatomy-stage__error">{loadError}</p>}
        <p className="anatomy-stage__attribution">Z-Anatomy model · GLB</p>
        <div ref={tooltipRef} className="anatomy-tooltip" role="status" />
      </section>

      {panelOpen && selectedAnatomy && (
        <aside ref={infoPanelRef} className="anatomy-info" aria-label="Selected anatomy details">
          <header className="anatomy-info__header">
            <div>
              <p className="anatomy-info__context">{selection.system} anatomy</p>
              <h2>{displayAnatomyName(selection.name)}</h2>
            </div>
            <button type="button" className="anatomy-info__close" onClick={() => onDismissRef.current?.()}>Close</button>
          </header>
          <section className="anatomy-info__section">
            <p className="anatomy-info__label">Scientific context</p>
            <h3>{selectedAnatomy.scientificName}</h3>
            <p>{selectedAnatomy.summary}</p>
          </section>
          <section className="anatomy-info__section">
            <p className="anatomy-info__label">Common pain contributors</p>
            <h3>Patterns worth discussing</h3>
            <ul>{selectedAnatomy.causes.map((cause) => <li key={cause}>{cause}</li>)}</ul>
          </section>
          <section className="anatomy-info__section">
            <p className="anatomy-info__label">Movement ideas</p>
            <h3>General rehabilitation examples</h3>
            <ul>{selectedAnatomy.rehab.map((exercise) => <li key={exercise}>{exercise}</li>)}</ul>
            <p className="anatomy-info__disclaimer">Educational information only. It is not a diagnosis or an individualized treatment plan.</p>
          </section>
        </aside>
      )}
    </main>
  );
}
