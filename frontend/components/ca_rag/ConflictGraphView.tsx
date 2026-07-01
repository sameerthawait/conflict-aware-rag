"use client";
import React, { useEffect, useState, useRef, useMemo } from "react";
import { GitCommit, RefreshCw, ZoomIn, ZoomOut } from "lucide-react";

interface ConflictGraphViewProps {
  response: any;
}

interface SimNode {
  id: string;
  label: string;
  source: string;
  stance: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface SimLink {
  source: string;
  target: string;
  type: "contradicts" | "supports" | "related";
  strength: number;
}

export default function ConflictGraphView({ response }: ConflictGraphViewProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [nodes, setNodes] = useState<SimNode[]>([]);
  const [links, setLinks] = useState<SimLink[]>([]);
  const [hoveredNode, setHoveredNode] = useState<SimNode | null>(null);
  const [draggedNodeId, setDraggedNodeId] = useState<string | null>(null);

  const { conflict_graph_json } = response;

  // Initialize nodes and links from graph JSON
  useEffect(() => {
    if (!conflict_graph_json) return;

    const rawNodes = conflict_graph_json.nodes || [];
    const rawLinks = conflict_graph_json.links || [];

    const width = 600;
    const height = 400;

    // Distribute nodes in a circle initially
    const simNodes: SimNode[] = rawNodes.map((n: any, idx: number) => {
      const angle = (idx / rawNodes.length) * 2 * Math.PI;
      return {
        id: n.id,
        label: n.label || "",
        source: n.source_title || n.source || "unknown",
        stance: n.stance || "unknown",
        x: width / 2 + Math.cos(angle) * 100,
        y: height / 2 + Math.sin(angle) * 100,
        vx: 0,
        vy: 0
      };
    });

    const simLinks: SimLink[] = rawLinks.map((l: any) => ({
      source: l.source,
      target: l.target,
      type: l.type || "related",
      strength: l.strength || 0.5
    }));

    setNodes(simNodes);
    setLinks(simLinks);
  }, [conflict_graph_json]);

  // Run a simple Verlet force-directed simulation loop
  useEffect(() => {
    if (nodes.length === 0) return;

    const width = 600;
    const height = 400;
    let animationId: number;

    const runFrame = () => {
      setNodes((currentNodes) => {
        // Create copies for computation
        const nextNodes = currentNodes.map((n) => ({ ...n }));

        // 1. Repulsion between all node pairs (charge)
        const chargeStrength = 200;
        for (let i = 0; i < nextNodes.length; i++) {
          for (let j = i + 1; j < nextNodes.length; j++) {
            const dx = nextNodes[j].x - nextNodes[i].x;
            const dy = nextNodes[j].y - nextNodes[i].y;
            const distSq = dx * dx + dy * dy + 0.1;
            const dist = Math.sqrt(distSq);

            if (dist < 200) {
              const force = chargeStrength / distSq;
              const fx = (dx / dist) * force;
              const fy = (dy / dist) * force;

              // Push nodes apart
              if (nextNodes[i].id !== draggedNodeId) {
                nextNodes[i].vx -= fx;
                nextNodes[i].vy -= fy;
              }
              if (nextNodes[j].id !== draggedNodeId) {
                nextNodes[j].vx += fx;
                nextNodes[j].vy += fy;
              }
            }
          }
        }

        // 2. Link attraction forces (springs)
        const restLength = 120;
        const springK = 0.04;
        links.forEach((link) => {
          const sNode = nextNodes.find((n) => n.id === link.source);
          const tNode = nextNodes.find((n) => n.id === link.target);

          if (sNode && tNode) {
            const dx = tNode.x - sNode.x;
            const dy = tNode.y - sNode.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 0.1;
            
            // Hooke's law: force proportional to displacement
            const displacement = dist - restLength;
            const force = displacement * springK * link.strength;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;

            if (sNode.id !== draggedNodeId) {
              sNode.vx += fx;
              sNode.vy += fy;
            }
            if (tNode.id !== draggedNodeId) {
              tNode.vx -= fx;
              tNode.vy -= fy;
            }
          }
        });

        // 3. Gravity pulling toward center
        const gravityK = 0.01;
        const cx = width / 2;
        const cy = height / 2;
        nextNodes.forEach((node) => {
          if (node.id === draggedNodeId) return;
          node.vx += (cx - node.x) * gravityK;
          node.vy += (cy - node.y) * gravityK;
        });

        // 4. Update positions with velocity and friction decay
        const friction = 0.85;
        nextNodes.forEach((node) => {
          if (node.id === draggedNodeId) return;
          node.vx *= friction;
          node.vy *= friction;
          node.x += node.vx;
          node.y += node.vy;

          // Keep in bounds
          node.x = Math.max(20, Math.min(width - 20, node.x));
          node.y = Math.max(20, Math.min(height - 20, node.y));
        });

        return nextNodes;
      });

      animationId = requestAnimationFrame(runFrame);
    };

    animationId = requestAnimationFrame(runFrame);
    return () => cancelAnimationFrame(animationId);
  }, [nodes.length, links, draggedNodeId]);

  // Handle Drag Events
  const handleMouseDown = (nodeId: string) => {
    setDraggedNodeId(nodeId);
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!draggedNodeId || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    setNodes((currentNodes) =>
      currentNodes.map((node) =>
        node.id === draggedNodeId
          ? { ...node, x: mouseX, y: mouseY, vx: 0, vy: 0 }
          : node
      )
    );
  };

  const handleMouseUp = () => {
    setDraggedNodeId(null);
  };

  const getNodeColor = (stance: string) => {
    if (stance.toLowerCase() === "supports") return "#171717"; // high-contrast black
    if (stance.toLowerCase() === "contradicts") return "#dc2626"; // red
    return "#a3a3a3"; // grey
  };

  return (
    <div className="space-y-4">
      {/* Description Header */}
      <div className="flex items-center justify-between pb-2 border-b border-neutral-100">
        <div className="flex items-center gap-2">
          <GitCommit size={16} className="text-neutral-500" />
          <span className="font-mono text-xs font-bold uppercase tracking-wider text-neutral-500">
            Interactive Contradiction Network
          </span>
        </div>
        <div className="flex gap-4 font-mono text-[9px] text-neutral-400">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-neutral-950" /> Supported Stance
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-red-600" /> Contradictory Link
          </span>
        </div>
      </div>

      <div className="relative border border-neutral-200 rounded overflow-hidden bg-neutral-50">
        {/* SVG Network Canvas */}
        <svg
          ref={svgRef}
          width="100%"
          height="400"
          viewBox="0 0 600 400"
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          className="cursor-grab active:cursor-grabbing select-none"
        >
          {/* Render Links */}
          {links.map((link, idx) => {
            const sNode = nodes.find((n) => n.id === link.source);
            const tNode = nodes.find((n) => n.id === link.target);
            if (!sNode || !tNode) return null;

            const isContradiction = link.type === "contradicts";

            return (
              <line
                key={idx}
                x1={sNode.x}
                y1={sNode.y}
                x2={tNode.x}
                y2={tNode.y}
                stroke={isContradiction ? "#fca5a5" : "#e5e5e5"}
                strokeWidth={isContradiction ? 2.5 : 1}
                strokeDasharray={isContradiction ? undefined : "3 3"}
              />
            );
          })}

          {/* Render Nodes */}
          {nodes.map((node) => (
            <circle
              key={node.id}
              cx={node.x}
              cy={node.y}
              r={hoveredNode?.id === node.id ? 10 : 7}
              fill={getNodeColor(node.stance)}
              stroke="#ffffff"
              strokeWidth={1.5}
              onMouseEnter={() => setHoveredNode(node)}
              onMouseLeave={() => setHoveredNode(null)}
              onMouseDown={() => handleMouseDown(node.id)}
              className="transition-all duration-150 cursor-pointer"
            />
          ))}
        </svg>

        {/* Hover Information Tooltip Overlay */}
        {hoveredNode && (
          <div className="absolute bottom-4 left-4 right-4 p-3 bg-white border border-neutral-200 rounded shadow-md pointer-events-none animate-fadeIn max-w-md">
            <span className="block font-mono text-[9px] font-bold text-neutral-400 uppercase tracking-wider">
              Claim ID: {hoveredNode.id.slice(0, 8)}... | Source: {hoveredNode.source}
            </span>
            <p className="font-sans text-xs text-neutral-800 font-medium leading-relaxed mt-1">
              "{hoveredNode.label}"
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
