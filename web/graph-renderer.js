/**
 * ForceGraph - D3 Force-Directed Knowledge Graph
 * Clean mesh/netlike distribution, no border constraints, natural color clustering
 */
class ForceGraph {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) { console.warn("ForceGraph: container", containerId, "not found"); return; }
        this.id = containerId;
        this.options = Object.assign({
            chargeStrength: -400,
            linkDistance: 160,
            collideRadius: 55,
            alphaDecay: 0.012,
            velocityDecay: 0.35,
            centerStrength: 0.03
        }, options);
        this._initSize();
        this._setupSVG();
        this._setupSimulation();
        this._setupZoom();
        this.nodes = [];
        this.edges = [];
        this.onNodeClick = options.onNodeClick || null;
    }

    _initSize() {
        let w = this.container.clientWidth;
        let h = this.container.clientHeight;
        if (w === 0 || h === 0) {
            const p = this.container.parentElement;
            if (p) { w = p.clientWidth || 960; h = p.clientHeight || 620; }
            else { w = 960; h = 620; }
        }
        this.width = Math.max(w, 700);
        this.height = Math.max(h, 500);
    }

    _nodeColor(node) {
        const dim = (node.radar_dimension_ids || []).join(",").toLowerCase();
        if (node.status === "root" || dim.includes("root")) return "#60a5fa";
        if (dim.includes("safety") || dim.includes("安全")) return "#f87171";
        if (dim.includes("sensor") || dim.includes("传感")) return "#fbbf24";
        if (dim.includes("plc") || dim.includes("控制") || dim.includes("plc")) return "#34d399";
        if (dim.includes("trouble") || dim.includes("故障") || dim.includes("排故")) return "#a78bfa";
        if (dim.includes("mechanical") || dim.includes("机械")) return "#fb923c";
        if (dim.includes("electrical") || dim.includes("电气")) return "#38bdf8";
        if (dim.includes("communication") || dim.includes("通信") || dim.includes("网络")) return "#f472b6";
        const colors = ["#60a5fa","#34d399","#fbbf24","#f87171","#a78bfa","#fb923c","#38bdf8","#f472b6"];
        const hash = (node.id || "").split("").reduce((a,c)=>a+c.charCodeAt(0),0);
        return colors[hash % colors.length];
    }

    _nodeRadius(node) {
        if (node.status === "root") return 38;
        const deg = Math.min(18, (node.degree || 0) * 2.5);
        const w = Math.min(14, (node.demand_weight || 0) * 5);
        return Math.max(16, 22 + deg + w);
    }

    // Distinct status ring styles for the outer stroke
    _statusRing(node) {
        const m = {
            core:      { color: "#22d3ee", width: 3.5, dash: "" },
            industry_hot: { color: "#f97316", width: 3.5, dash: "5,3" },
            industry:  { color: "#3b82f6", width: 2.5, dash: "" },
            weak:      { color: "#ef4444", width: 3.5, dash: "" },
            touched:   { color: "#818cf8", width: 2.5, dash: "" },
            improving: { color: "#06b6d4", width: 3, dash: "" },
            mastered:  { color: "#22c55e", width: 3.5, dash: "" },
            recommended_next: { color: "#f59e0b", width: 3, dash: "5,3" },
            unknown:   { color: "#64748b", width: 2, dash: "3,3" },
            root:      { color: "#60a5fa", width: 3, dash: "" }
        };
        return m[node.status] || { color: "#64748b", width: 2, dash: "" };
    }

    _setupSVG() {
        this.container.innerHTML = "";
        this.svg = d3.select(this.container)
            .append("svg")
            .attr("width", "100%")
            .attr("height", "100%")
            .attr("viewBox", [0, 0, this.width, this.height])
            .style("background", "#0f172a")
            .style("cursor", "grab");

        // Glow filter
        const defs = this.svg.append("defs");
        const glow = defs.append("filter").attr("id", `glow-${this.id}`).attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
        glow.append("feGaussianBlur").attr("stdDeviation", "3").attr("result", "blur");
        glow.append("feMerge").selectAll("feMergeNode").data(["blur","SourceGraphic"]).enter().append("feMergeNode").attr("in", d=>d);

        // Arrow marker
        defs.append("marker").attr("id", `arrow-${this.id}`).attr("viewBox", "0 -5 10 10").attr("refX", 32).attr("refY", 0)
            .attr("markerWidth", 6).attr("markerHeight", 6).attr("orient", "auto")
            .append("path").attr("d", "M0,-5L10,0L0,5").attr("fill", "#334155");

        this.g = this.svg.append("g");
    }

    _setupSimulation() {
        this.sim = d3.forceSimulation()
            .force("charge", d3.forceManyBody().strength(this.options.chargeStrength))
            .force("link", d3.forceLink().id(d => d.id).distance(this.options.linkDistance))
            .force("collide", d3.forceCollide().radius(d => (d.radius || 22) + this.options.collideRadius * 0.5))
            .force("center", d3.forceCenter(this.width / 2, this.height / 2).strength(this.options.centerStrength))
            .alphaDecay(this.options.alphaDecay)
            .velocityDecay(this.options.velocityDecay);
    }

    _setupZoom() {
        this.zoom = d3.zoom()
            .scaleExtent([0.3, 4])
            .on("zoom", (ev) => { this.g.attr("transform", ev.transform); });
        this.svg.call(this.zoom);
        this.svg.call(this.zoom.transform, d3.zoomIdentity.translate(-20, -20).scale(0.85));
    }

    _buildGraphData(graphData) {
        const nodes = (graphData?.nodes || []).map((n, i) => {
            const radius = this._nodeRadius(n);
            const color = this._nodeColor(n);
            return {
                ...n,
                index: i,
                radius: radius,
                color: color,
                x: (this.width / 2) + (Math.random() - 0.5) * this.width * 0.6,
                y: (this.height / 2) + (Math.random() - 0.5) * this.height * 0.6
            };
        });

        const edges = [];
        const edgeSet = new Set();
        const addEdge = (src, tgt) => {
            if (!src || !tgt || src === tgt) return;
            const key = [src, tgt].sort().join("||");
            if (edgeSet.has(key)) return;
            edgeSet.add(key);
            edges.push({ source: src, target: tgt });
        };

        const groups = {};
        nodes.forEach(n => {
            (n.radar_dimension_ids || ["_"]).forEach(dim => {
                if (!groups[dim]) groups[dim] = [];
                groups[dim].push(n.id);
            });
        });

        Object.values(groups).forEach(group => {
            for (let i = 0; i < group.length; i++) {
                for (let j = i + 1; j < group.length; j++) {
                    addEdge(group[i], group[j]);
                }
            }
        });

        const root = nodes.find(n => n.status === "root" || n.is_virtual);
        if (root) {
            nodes.forEach(n => {
                if (n.id !== root.id) addEdge(n.id, root.id);
            });
        }

        const connected = new Set(edges.flatMap(e => [e.source, e.target]));
        nodes.forEach(n => {
            if (!connected.has(n.id) && root && n.id !== root.id) {
                addEdge(n.id, root.id);
            }
        });

        return { nodes, edges, graphData };
    }

    update(graphData) {
        if (!this.svg) return;

        const { nodes, edges } = this._buildGraphData(graphData);
        if (!nodes.length) {
            this.g.selectAll("*").remove();
            this.g.append("text").attr("x", this.width/2).attr("y", this.height/2)
                .attr("text-anchor", "middle").attr("fill", "#64748b").attr("font-size", "15")
                .text("暂无图谱数据");
            return;
        }

        // EDGES
        const link = this.g.selectAll(".edge").data(edges, d => `${d.source.id||d.source}||${d.target.id||d.target}`);
        link.exit().remove();
        const linkEnter = link.enter().append("path").attr("class", "edge")
            .attr("fill", "none")
            .attr("stroke", "#1e293b")
            .attr("stroke-width", 1.5)
            .attr("marker-end", `url(#arrow-${this.id})`);
        this.selEdges = linkEnter.merge(link);

        // NODE GROUPS
        const ng = this.g.selectAll(".node").data(nodes, d => d.id);
        ng.exit().remove();

        const ngEnter = ng.enter().append("g").attr("class", "node")
            .attr("cursor", "pointer")
            .call(d3.drag()
                .on("start", (ev, d) => {
                    if (!ev.active) this.sim.alphaTarget(0.3).restart();
                    d.fx = d.x; d.fy = d.y;
                })
                .on("drag", (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
                .on("end", (ev, d) => {
                    if (!ev.active) this.sim.alphaTarget(0);
                    d.fx = null; d.fy = null;
                })
            );

        // Outer glow circle
        ngEnter.append("circle").attr("class", "node-glow")
            .attr("r", d => d.radius + 10)
            .attr("fill", d => d.color)
            .attr("opacity", 0.08)
            .attr("filter", `url(#glow-${this.id})`);

        // Status outer ring - thick, distinct color per status
        ngEnter.append("circle").attr("class", "node-status-ring")
            .attr("r", d => d.radius + 5)
            .attr("fill", "none")
            .attr("stroke", d => this._statusRing(d).color)
            .attr("stroke-width", d => this._statusRing(d).width)
            .attr("stroke-dasharray", d => this._statusRing(d).dash)
            .attr("opacity", 0.85);

        // Main node circle
        ngEnter.append("circle").attr("class", "node-circle")
            .attr("r", d => d.radius)
            .attr("fill", d => d.color)
            .attr("stroke", d => d3.color(d.color).darker(0.3))
            .attr("stroke-width", 1.5)
            .attr("opacity", 0.92);

        // Inner highlight
        ngEnter.append("circle").attr("class", "node-inner")
            .attr("r", d => d.radius * 0.4)
            .attr("fill", "rgba(255,255,255,0.22)");

        // Label group (background + text)
        const lg = ngEnter.append("g").attr("class", "label-group");

        // Label text
        const lbl = lg.append("text").attr("class", "node-label")
            .attr("text-anchor", "middle")
            .attr("fill", "#e2e8f0")
            .attr("font-size", "13")
            .attr("font-family", "system-ui, -apple-system, sans-serif")
            .attr("font-weight", "500")
            .attr("pointer-events", "none");

        lbl.each(function(d) {
            const text = d3.select(this);
            const name = d.label || d.name || d.id || "";
            const lines = ForceGraph._wrapLabel(name, 9);
            lines.forEach((line, i) => {
                text.append("tspan")
                    .attr("x", 0)
                    .attr("dy", i === 0 ? 0 : 15)
                    .attr("fill", d.status === "root" ? "#e2e8f0" : "#e2e8f0")
                    .attr("font-weight", d.status === "root" ? "700" : "500")
                    .text(line);
            });
            d._labelLines = lines;
            d._labelWidth = Math.max(...lines.map(l => l.length)) * 8 + 20;
            d._labelHeight = lines.length * 15 + 10;
        });


        this.selNodes = ngEnter.merge(ng);

        // Click handler
        if (this.onNodeClick) {
            this.selNodes.on("click", (ev, d) => {
                ev.stopPropagation();
                this.onNodeClick(d, graphData);
            });
        }

        // Hover effects
        this.selNodes.on("mouseenter", function() {
            d3.select(this).select(".node-circle").transition().duration(200).attr("opacity", 1).attr("stroke-width", 2.5);
            d3.select(this).select(".node-glow").transition().duration(200).attr("opacity", 0.22);
            d3.select(this).select(".node-status-ring").transition().duration(200).attr("opacity", 1);
        }).on("mouseleave", function() {
            d3.select(this).select(".node-circle").transition().duration(200).attr("opacity", 0.92).attr("stroke-width", 1.5);
            d3.select(this).select(".node-glow").transition().duration(200).attr("opacity", 0.08);
            d3.select(this).select(".node-status-ring").transition().duration(200).attr("opacity", 0.85);
        });

        // Simulation
        this.sim.nodes(nodes);
        this.sim.force("link").links(edges);
        this.sim.alpha(0.7).restart();

        this.sim.on("tick", () => {
            this.selEdges.attr("d", d => {
                const sx = d.source.x, sy = d.source.y;
                const tx = d.target.x, ty = d.target.y;
                const dx = tx - sx, dy = ty - sy;
                const dist = Math.sqrt(dx*dx + dy*dy) || 1;
                const curve = Math.min(dist * 0.12, 35);
                const mx = (sx+tx)/2 - (dy/dist)*curve;
                const my = (sy+ty)/2 + (dx/dist)*curve;
                return `M${sx},${sy} Q${mx},${my} ${tx},${ty}`;
            });
            this.selNodes.attr("transform", d => `translate(${d.x},${d.y})`);
        });
    }

    static _wrapLabel(text, maxChars) {
        const value = String(text || "");
        const lines = [];
        for (let i = 0; i < value.length; i += maxChars) {
            lines.push(value.slice(i, i + maxChars));
        }
        if (lines.length > 2) {
            const t = lines.slice(0, 2);
            t[1] = t[1].slice(0, Math.max(1, maxChars - 2)) + "..";
            return t;
        }
        return lines.length ? lines : [""];
    }

    resize() {
        this._initSize();
        this.svg.attr("viewBox", [0, 0, this.width, this.height]);
        this.sim.force("center", d3.forceCenter(this.width/2, this.height/2).strength(this.options.centerStrength));
        this.sim.alpha(0.4).restart();
    }

    destroy() {
        this.sim?.stop();
        this.svg?.remove();
    }
}


