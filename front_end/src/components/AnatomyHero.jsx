import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

// Same Blender export the mapping screen uses, so loading it here also warms the cache.
const MODEL_URL = "/models/zanatomy_split.glb";
// Fasciae and bursae wrap the muscles in a continuous shell; hide them so the muscles show.
const CONNECTIVE_NAME = /fascia|ligament|tendon|retinaculum|bursa|sheath|aponeurosis|septum|band|capsule/i;

// Sample pain sites, keyed by the exact Blender object names in the GLB.
// Each one reads like a line from a generated report.
const HOTSPOTS = [
  { mesh: "Acromial part of deltoid muscle.l", label: "L. deltoid, acromial", detail: "6/10 · sharp · on lifting" },
  { mesh: "Descending part of trapezius muscle.r", label: "R. upper trapezius", detail: "5/10 · aching · constant" },
  { mesh: "Latissimus dorsi muscle.l", label: "L. latissimus dorsi", detail: "7/10 · aching · 3 weeks" },
  { mesh: "Vastus medialis muscle.r", label: "R. vastus medialis", detail: "4/10 · dull · on stairs" },
];

const vertexShader = /* glsl */ `
  varying vec3 vWorld;
  varying vec3 vNormalV;
  varying vec3 vViewDir;
  void main() {
    vec4 world = modelMatrix * vec4(position, 1.0);
    vec4 view = viewMatrix * world;
    vWorld = world.xyz;
    vNormalV = normalize(normalMatrix * normal);
    vViewDir = -view.xyz;
    gl_Position = projectionMatrix * view;
  }
`;

// Unscanned tissue reads as topographic contour lines; once the scan line
// passes, it resolves into a lit, solid form. Pain sites glow in the accent.
const fragmentShader = /* glsl */ `
  uniform float uTime;
  uniform float uReveal;
  uniform float uLine;
  uniform float uHot;
  uniform float uHotOn;
  uniform float uPhase;
  uniform vec3 uBone;
  uniform vec3 uShadow;
  uniform vec3 uAccent;
  varying vec3 vWorld;
  varying vec3 vNormalV;
  varying vec3 vViewDir;

  float contour(float value, float density) {
    float y = value * density;
    float d = abs(fract(y - 0.5) - 0.5) / max(fwidth(y), 1e-4);
    return 1.0 - min(d, 1.0);
  }

  void main() {
    vec3 n = normalize(vNormalV);
    if (!gl_FrontFacing) n = -n;
    vec3 v = normalize(vViewDir);
    float ndv = clamp(dot(n, v), 0.0, 1.0);
    float fres = pow(1.0 - ndv, 2.4);
    float key = clamp(dot(n, normalize(vec3(-0.45, 0.55, 0.7))), 0.0, 1.0);
    float back = clamp(dot(n, normalize(vec3(0.7, 0.2, -0.6))), 0.0, 1.0);

    float lines = contour(vWorld.y, 110.0);
    float revealed = smoothstep(uReveal - 0.012, uReveal + 0.012, vWorld.y);

    vec3 ghost = uBone * (lines * 0.22 + fres * 0.2);

    vec3 solid = mix(uShadow, uBone * 0.82, key * 0.78 + 0.06);
    solid += uBone * back * 0.06;
    solid += uBone * fres * 0.32;
    solid *= 1.0 - lines * 0.08;

    float pulse = 0.5 + 0.5 * sin(uTime * 2.2 + uPhase);
    float hot = uHot * uHotOn;
    vec3 hotColor = uAccent * (0.32 + key * 0.75) + uAccent * fres * (0.55 + 0.45 * pulse);
    solid = mix(solid, hotColor, hot * 0.92);

    vec3 color = mix(ghost, solid, revealed);

    float band = exp(-pow((vWorld.y - uLine) * 160.0, 2.0));
    color += uBone * band * 0.9;

    gl_FragColor = vec4(color, 1.0);
    #include <colorspace_fragment>
  }
`;

export default function AnatomyHero() {
  const wrapRef = useRef(null);
  const hostRef = useRef(null);
  const labelRefs = useRef([]);
  const rulerMarkRef = useRef(null);
  const rulerValueRef = useRef(null);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    const wrap = wrapRef.current;
    const host = hostRef.current;
    if (!wrap || !host) return undefined;

    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    } catch {
      setStatus("error");
      return undefined;
    }

    let disposed = false;
    let frame = 0;
    let visible = true;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const finePointer = window.matchMedia("(pointer: fine)").matches;

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor(0x000000, 0);
    host.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(24, 1, 0.05, 40);
    const lookTarget = new THREE.Vector3(0, 0.9, 0);

    const turntable = new THREE.Group();
    scene.add(turntable);
    const body = new THREE.Group();
    turntable.add(body);

    const sharedUniforms = {
      uTime: { value: 0 },
      uReveal: { value: 10 },
      uLine: { value: 10 },
    };
    const palette = {
      uBone: { value: new THREE.Color("#ece7de") },
      uShadow: { value: new THREE.Color("#141311") },
      uAccent: { value: new THREE.Color("#ff5b3a") },
    };
    const makeMaterial = (hot, phase = 0) =>
      new THREE.ShaderMaterial({
        vertexShader,
        fragmentShader,
        uniforms: {
          ...sharedUniforms,
          ...palette,
          uHot: { value: hot ? 1 : 0 },
          uHotOn: { value: 0 },
          uPhase: { value: phase },
        },
      });
    const baseMaterial = makeMaterial(false);
    const materials = [baseMaterial];

    // Floor ring with tick marks, like the bed of an instrument.
    const floor = new THREE.Group();
    const ringMaterial = new THREE.LineBasicMaterial({ color: 0xece7de, transparent: true, opacity: 0.16 });
    const tickMaterial = new THREE.LineBasicMaterial({ color: 0xece7de, transparent: true, opacity: 0.28 });
    const ringPoints = [];
    for (let i = 0; i <= 160; i += 1) {
      const a = (i / 160) * Math.PI * 2;
      ringPoints.push(new THREE.Vector3(Math.cos(a) * 0.62, 0, Math.sin(a) * 0.62));
    }
    const ring = new THREE.Line(new THREE.BufferGeometry().setFromPoints(ringPoints), ringMaterial);
    floor.add(ring);
    const tickPoints = [];
    for (let i = 0; i < 72; i += 1) {
      const a = (i / 72) * Math.PI * 2;
      const inner = i % 6 === 0 ? 0.56 : 0.595;
      tickPoints.push(new THREE.Vector3(Math.cos(a) * inner, 0, Math.sin(a) * inner));
      tickPoints.push(new THREE.Vector3(Math.cos(a) * 0.62, 0, Math.sin(a) * 0.62));
    }
    const ticks = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(tickPoints), tickMaterial);
    floor.add(ticks);
    turntable.add(floor);

    const hotspots = [];
    let bounds = null;
    let introStart = -1;
    const clock = new THREE.Clock();

    const resize = () => {
      const width = Math.max(host.clientWidth, 1);
      const height = Math.max(host.clientHeight, 1);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      // Fit the full body height with a little air above and below.
      const fitHeight = bounds ? bounds.max.y - bounds.min.y : 1.8;
      const vFov = THREE.MathUtils.degToRad(camera.fov);
      let distance = (fitHeight * 1.16) / (2 * Math.tan(vFov / 2));
      if (camera.aspect < 0.55) distance *= 0.55 / camera.aspect;
      camera.position.set(0, lookTarget.y + 0.12, distance);
      camera.lookAt(lookTarget);
      camera.updateProjectionMatrix();
      if (!frame && visible && !disposed) frame = requestAnimationFrame(render);
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);

    const visibility = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible && !frame && !disposed) frame = requestAnimationFrame(render);
    });
    visibility.observe(wrap);

    const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
    const onPointerMove = (event) => {
      const rect = wrap.getBoundingClientRect();
      pointer.tx = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.ty = ((event.clientY - rect.top) / rect.height) * 2 - 1;
    };
    if (finePointer && !reduceMotion) window.addEventListener("pointermove", onPointerMove, { passive: true });

    new GLTFLoader()
      .loadAsync(MODEL_URL, (event) => {
        if (event.lengthComputable && !disposed) setProgress(Math.round((event.loaded / event.total) * 100));
      })
      .then((gltf) => {
        if (disposed) return;
        const hotIndex = new Map(HOTSPOTS.map((spot, index) => [spot.mesh, index]));

        gltf.scene.traverse((object) => {
          if (!object.isMesh) return;
          const original = object.material;
          (Array.isArray(original) ? original : [original]).forEach((material) => material.dispose());
          object.material = baseMaterial;
        });

        gltf.scene.children.forEach((node) => {
          const name = node.userData.name || node.name;
          if (CONNECTIVE_NAME.test(name)) node.visible = false;
          if (!hotIndex.has(name)) return;
          const index = hotIndex.get(name);
          const material = makeMaterial(true, index * 1.7);
          materials.push(material);
          node.traverse((object) => {
            if (object.isMesh) object.material = material;
          });
          hotspots[index] = { node, material, center: new THREE.Vector3(), shown: false };
        });

        body.add(gltf.scene);
        body.updateMatrixWorld(true);
        bounds = new THREE.Box3().setFromObject(body);
        const center = bounds.getCenter(new THREE.Vector3());
        // Center on the vertical axis and stand the figure on the floor ring.
        body.position.set(-center.x, -bounds.min.y, -center.z);
        body.updateMatrixWorld(true);
        bounds = new THREE.Box3().setFromObject(body);
        lookTarget.set(0, (bounds.max.y + bounds.min.y) / 2, 0);
        const footprint = Math.max(bounds.max.x - bounds.min.x, bounds.max.z - bounds.min.z);
        floor.scale.setScalar((footprint * 0.62) / 0.62);

        hotspots.forEach((spot) => {
          if (!spot) return;
          new THREE.Box3().setFromObject(spot.node).getCenter(spot.center);
          spot.center.applyMatrix4(body.matrixWorld.clone().invert());
        });

        resize();
        introStart = clock.getElapsedTime();
        setStatus("ready");
      })
      .catch(() => {
        if (!disposed) setStatus("error");
      });

    const worldPoint = new THREE.Vector3();
    const outward = new THREE.Vector3();
    const toCamera = new THREE.Vector3();
    const screenPoint = new THREE.Vector3();

    const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

    function render() {
      frame = 0;
      if (disposed || !visible) return;

      const elapsed = clock.getElapsedTime();
      sharedUniforms.uTime.value = elapsed;

      pointer.x += (pointer.tx - pointer.x) * 0.04;
      pointer.y += (pointer.ty - pointer.y) * 0.04;

      if (bounds) {
        const top = bounds.max.y + 0.04;
        const bottom = bounds.min.y - 0.04;
        const sinceIntro = elapsed - introStart;
        const introLength = 3.6;

        if (reduceMotion) {
          sharedUniforms.uReveal.value = bottom - 1;
          sharedUniforms.uLine.value = bottom - 1;
        } else if (sinceIntro < introLength) {
          const t = easeInOut(Math.min(sinceIntro / introLength, 1));
          const y = THREE.MathUtils.lerp(top, bottom, t);
          sharedUniforms.uReveal.value = y;
          sharedUniforms.uLine.value = y;
        } else {
          sharedUniforms.uReveal.value = bottom - 1;
          // Periodic quiet pass of the scan line after the intro reveal.
          const cycle = 9;
          const local = ((sinceIntro - introLength) % cycle) - (cycle - 3.2);
          sharedUniforms.uLine.value = local > 0 ? THREE.MathUtils.lerp(top, bottom, easeInOut(local / 3.2)) : bottom - 1;
        }

        const spin = reduceMotion ? 0.5 : elapsed * 0.16;
        turntable.rotation.y = spin + pointer.x * 0.35;
        turntable.rotation.x = pointer.y * 0.04;
        turntable.updateMatrixWorld(true);

        const width = host.clientWidth;
        const height = host.clientHeight;

        // Height ruler marker follows whichever line is lower: the active scan or nothing.
        const lineY = sharedUniforms.uLine.value;
        const lineActive = lineY > bottom - 0.5;
        if (rulerMarkRef.current) {
          screenPoint.set(0, lineActive ? lineY : bottom, 0).project(camera);
          rulerMarkRef.current.style.transform = `translate3d(0, ${((1 - screenPoint.y) / 2) * height}px, 0)`;
          rulerMarkRef.current.style.opacity = lineActive ? "1" : "0";
        }
        if (rulerValueRef.current && lineActive) {
          // The Blender export is in metres.
          const cm = Math.max(0, Math.round((lineY - bounds.min.y) * 100));
          rulerValueRef.current.textContent = `${String(cm).padStart(3, "0")} cm`;
        }

        toCamera.copy(camera.position).setY(0).normalize();
        hotspots.forEach((spot, index) => {
          const label = labelRefs.current[index];
          if (!spot || !label) return;
          worldPoint.copy(spot.center).applyMatrix4(body.matrixWorld);

          const scanned = sharedUniforms.uReveal.value < worldPoint.y;
          spot.material.uniforms.uHotOn.value += ((scanned ? 1 : 0) - spot.material.uniforms.uHotOn.value) * 0.08;

          outward.set(worldPoint.x, 0, worldPoint.z * 2.4);
          const facing = outward.lengthSq() > 1e-5 ? outward.normalize().dot(toCamera) : 1;
          const show = scanned && facing > 0.12;

          screenPoint.copy(worldPoint).project(camera);
          const x = ((screenPoint.x + 1) / 2) * width;
          const y = ((1 - screenPoint.y) / 2) * height;
          const side = x < width / 2 ? "left" : "right";
          label.style.transform = `translate3d(${x}px, ${y}px, 0)`;
          if (label.dataset.side !== side) label.dataset.side = side;
          if (show !== spot.shown) {
            spot.shown = show;
            label.classList.toggle("is-visible", show);
          }
        });
      }

      renderer.render(scene, camera);
      if (!reduceMotion || !bounds) frame = requestAnimationFrame(render);
    }
    frame = requestAnimationFrame(render);

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      visibility.disconnect();
      window.removeEventListener("pointermove", onPointerMove);
      body.traverse((object) => object.geometry?.dispose());
      materials.forEach((material) => material.dispose());
      ring.geometry.dispose();
      ticks.geometry.dispose();
      ringMaterial.dispose();
      tickMaterial.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return (
    <div ref={wrapRef} className={`anatomy-hero is-${status}`} aria-hidden="true">
      <div ref={hostRef} className="anatomy-hero__canvas" />

      <div className="anatomy-hero__ruler">
        <div ref={rulerMarkRef} className="anatomy-hero__ruler-mark">
          <span ref={rulerValueRef} />
        </div>
      </div>

      {HOTSPOTS.map((spot, index) => (
        <div
          key={spot.mesh}
          ref={(element) => { labelRefs.current[index] = element; }}
          className="anatomy-hero__label"
          data-side="right"
        >
          <span className="anatomy-hero__dot" />
          <span className="anatomy-hero__leader" />
          <span className="anatomy-hero__tag">
            <span className="anatomy-hero__tag-name">{spot.label}</span>
            <span className="anatomy-hero__tag-detail">{spot.detail}</span>
          </span>
        </div>
      ))}

      {status === "loading" && (
        <div className="anatomy-hero__loading">
          <span>Loading anatomy model</span>
          <span className="anatomy-hero__loading-bar">
            <span style={{ transform: `scaleX(${progress / 100})` }} />
          </span>
          <span>{String(progress).padStart(2, "0")}%</span>
        </div>
      )}
    </div>
  );
}
