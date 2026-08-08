import {
  arc,
  axisBottom,
  axisLeft,
  curveMonotoneX,
  line,
  max,
  pie,
  scaleBand,
  scaleLinear,
  scalePoint,
  select,
} from "d3";

function formatted(value, unit) {
  if (value === null || value === undefined) return "–";
  const digits = unit === "%" ? 1 : 2;
  const number = new Intl.NumberFormat("de-AT", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value) || 0);
  return `${number} ${unit}`;
}

function compactLabel(label) {
  if (label.includes("EEG")) return "EEG";
  if (label.includes("Netz")) return "Netz";
  return label.length > 11 ? `${label.slice(0, 10)}…` : label;
}

function compactCategoryLabel(label) {
  if (label.includes("Verbrauch")) return "Verbrauch";
  if (label.includes("Einspeisung")) return "Einspeisung";
  return label.length > 16 ? `${label.slice(0, 15)}…` : label;
}

function colorFor(item, index) {
  return item.colors?.[index] || item.color;
}

function legend(host, items) {
  const row = select(host).append("div").attr("class", "legend");
  const entries = row.selectAll("span").data(items).join("span").attr("class", "legend-item");
  entries.append("span").attr("class", "dot").style("background", (item) => item.color);
  entries.append("span").text((item) => item.label);
}

function detail(host, payload, index) {
  const category = payload.categories[index];
  if (!category) return;
  const box = select(host).selectAll(".detail").data([category]).join("div").attr("class", "detail");
  box.selectAll("*").remove();
  box.append("div")
    .attr("class", `detail-title${category.estimated ? " estimated" : ""}`)
    .text(`${category.detail}${category.estimated ? " · Ersatzwert" : ""}`);
  const values = box.append("div").attr("class", "detail-values");
  const rows = values.selectAll("span").data(payload.series).join("span").attr("class", "detail-value");
  rows.append("span").style("color", (item) => item.color).text("● ");
  rows.append("span").text((item) => `${item.label}: ${formatted(item.values[index], payload.unit)}`);
}

function renderBars(host, payload) {
  const viewportWidth = Math.max(240, host.clientWidth || 360);
  const minimumCategoryWidth = payload.categories.length > 48 ? 18
    : payload.categories.length > 31 ? 14 : 12;
  const width = Math.max(viewportWidth, payload.categories.length * minimumCategoryWidth + 50);
  const height = 200;
  const margin = { top: 10, right: 18, bottom: 32, left: 46 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const stackNames = [...new Set(payload.series.map((item) => item.stack))];
  const totals = payload.categories.flatMap((_, index) => stackNames.map((stack) =>
    payload.series
      .filter((item) => item.stack === stack)
      .reduce((sum, item) => sum + Math.max(0, Number(item.values[index]) || 0), 0)
  ));
  const upper = max(totals) || 1;
  const x = scaleBand().domain(payload.categories.map((_, index) => String(index))).range([0, innerWidth]).padding(0.18);
  const group = scaleBand().domain(stackNames).range([0, x.bandwidth()]).padding(0.10);
  const y = scaleLinear().domain([0, upper]).nice().range([innerHeight, 0]);
  const scroller = select(host).append("div").attr("class", "plot-scroll");
  const svg = scroller.append("svg")
    .attr("viewBox", [0, 0, width, height])
    .attr("width", width)
    .attr("height", height)
    .attr("role", "img")
    .attr("aria-label", `Energiediagramm in ${payload.unit}`);
  const plot = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  plot.append("g").attr("class", "grid")
    .call(axisLeft(y).ticks(4).tickSize(-innerWidth).tickFormat(""));
  plot.append("g").attr("class", "axis")
    .call(axisLeft(y).ticks(4).tickFormat((value) => new Intl.NumberFormat("de-AT", {
      maximumFractionDigits: 2,
    }).format(value)));

  const maxTicks = Math.max(3, Math.floor(innerWidth / 66));
  const tickStep = Math.max(1, Math.ceil(payload.categories.length / maxTicks));
  plot.append("g")
    .attr("class", "axis")
    .attr("transform", `translate(0,${innerHeight})`)
    .call(axisBottom(x).tickValues(payload.categories.map((_, index) => String(index)).filter((_, index) => index % tickStep === 0))
      .tickFormat((index) => payload.categories[Number(index)]?.label || ""));

  payload.categories.forEach((_, categoryIndex) => {
    stackNames.forEach((stack) => {
      let offset = 0;
      payload.series.filter((item) => item.stack === stack).forEach((item) => {
        const value = Math.max(0, Number(item.values[categoryIndex]) || 0);
        plot.append("rect")
          .attr("class", "bar")
          .attr("x", (x(String(categoryIndex)) || 0) + (group(stack) || 0))
          .attr("y", y(offset + value))
          .attr("width", Math.max(1, group.bandwidth()))
          .attr("height", Math.max(0, y(offset) - y(offset + value)))
          .attr("rx", Math.min(3, group.bandwidth() / 3))
          .attr("fill", colorFor(item, categoryIndex))
          .attr("opacity", payload.categories[categoryIndex].estimated ? 0.58 : 0.90);
        offset += value;
      });
    });
  });

  const marker = plot.append("line")
    .attr("y1", 0).attr("y2", innerHeight)
    .attr("stroke", "currentColor").attr("stroke-dasharray", "3 3")
    .attr("opacity", 0);
  plot.selectAll(".touch-target")
    .data(payload.categories)
    .join("rect")
    .attr("class", "touch-target")
    .attr("x", (_, index) => x(String(index)) || 0)
    .attr("width", x.bandwidth())
    .attr("height", innerHeight)
    .attr("fill", "transparent")
    .on("click", (_, category) => {
      const index = payload.categories.indexOf(category);
      marker.attr("x1", (x(String(index)) || 0) + x.bandwidth() / 2)
        .attr("x2", (x(String(index)) || 0) + x.bandwidth() / 2)
        .attr("opacity", 0.55);
      detail(host, payload, index);
    });

  legend(host, payload.series);
  if (payload.categories.length) detail(host, payload, payload.categories.length - 1);
}

function renderDonuts(host, payload) {
  const width = Math.max(240, host.clientWidth || 360);
  const count = Math.max(1, payload.categories.length);
  const slotWidth = width / count;
  const radius = count > 1
    ? Math.min(61, slotWidth * 0.34)
    : Math.min(82, slotWidth * 0.29);
  const centerY = 120;
  const height = 210;
  const layout = pie().sort(null).value((item) => item.value);
  const shape = arc()
    .innerRadius(radius * 0.58)
    .outerRadius(radius)
    .cornerRadius(5)
    .padAngle(0.018);
  const svg = select(host).append("svg")
    .attr("viewBox", [0, 0, width, height])
    .attr("width", "100%")
    .attr("height", height)
    .attr("role", "img")
    .attr("aria-label", "Interaktive EEG- und Netzanteile der Energiebilanz");
  const details = select(host).append("div")
    .attr("class", "donut-details")
    .style("grid-template-columns", `repeat(${count}, minmax(0, 1fr))`);
  const detailBoxes = details.selectAll("div")
    .data(payload.categories)
    .join("div")
    .attr("class", "donut-detail");

  payload.categories.forEach((category, categoryIndex) => {
    const values = payload.series.map((item) => ({
      ...item,
      color: colorFor(item, categoryIndex),
      value: Math.max(0, Number(item.values[categoryIndex]) || 0),
    }));
    const total = values.reduce((sum, item) => sum + item.value, 0);
    const arcs = layout(values);
    const centerX = slotWidth * (categoryIndex + 0.5);

    svg.append("text")
      .attr("x", centerX).attr("y", 18).attr("text-anchor", "middle")
      .attr("font-size", count > 1 ? 13 : 15).attr("font-weight", 650)
      .text(compactCategoryLabel(category.label));

    const totalText = svg.append("text")
      .attr("x", centerX).attr("y", 43).attr("text-anchor", "middle")
      .attr("font-size", count > 1 ? 18 : 20).attr("font-weight", 700)
      .style("font-variant-numeric", "tabular-nums");
    totalText.append("tspan")
      .text(new Intl.NumberFormat("de-AT", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(total));
    totalText.append("tspan")
      .attr("dx", 4).attr("font-size", 11).attr("font-weight", 550).attr("opacity", 0.68)
      .text(payload.unit);

    const depth = svg.append("g")
      .attr("transform", `translate(${centerX},${centerY + 5}) scale(1,0.92)`);
    depth.selectAll("path").data(arcs).join("path")
      .attr("d", shape)
      .attr("fill", (item) => item.data.color)
      .attr("opacity", 0.48)
      .style("filter", "brightness(0.58)");

    const top = svg.append("g")
      .attr("class", "donut-top")
      .attr("transform", `translate(${centerX},${centerY}) scale(1,0.92)`);
    const paths = top.selectAll("path").data(arcs).join("path")
      .attr("d", shape)
      .attr("fill", (item) => item.data.color)
      .attr("stroke", "rgba(255,255,255,.72)")
      .attr("stroke-width", 1.2)
      .attr("opacity", category.estimated ? 0.68 : 0.96)
      .style("cursor", "pointer");

    const centerValue = svg.append("text")
      .attr("x", centerX).attr("y", centerY - 2).attr("text-anchor", "middle")
      .attr("font-size", count > 1 ? 17 : 24).attr("font-weight", 700)
      .style("font-variant-numeric", "tabular-nums");
    const centerLabel = svg.append("text")
      .attr("x", centerX).attr("y", centerY + 17).attr("text-anchor", "middle")
      .attr("font-size", 12).attr("font-weight", 600).attr("opacity", 0.70);

    function selectSlice(item) {
      const percentage = total > 0 ? item.data.value / total * 100 : 0;
      paths.attr("opacity", (candidate) => candidate === item ? 1 : 0.28)
        .attr("stroke-width", (candidate) => candidate === item ? 2 : 1.2);
      centerValue.text(`${new Intl.NumberFormat("de-AT", { maximumFractionDigits: 1 }).format(percentage)} %`);
      centerLabel.text(compactLabel(item.data.label));
      select(detailBoxes.nodes()[categoryIndex])
        .text(`${compactLabel(item.data.label)} · ${formatted(item.data.value, payload.unit)}`);
    }

    paths.on("click", (_, item) => selectSlice(item));
    selectSlice(arcs[0]);
    values.forEach((item, itemIndex) => {
      const direction = itemIndex === 0 ? -1 : 1;
      svg.append("text")
        .attr("x", centerX + direction * Math.min(36, slotWidth * 0.22)).attr("y", 198)
        .attr("text-anchor", "middle")
        .attr("font-size", 11).attr("font-weight", 650).attr("opacity", 0.88)
        .style("fill", item.color)
        .text(compactLabel(item.label));
    });
  });
}

function renderLines(host, payload) {
  const width = Math.max(260, host.clientWidth || 360);
  const height = 210;
  const margin = { top: 10, right: 18, bottom: 34, left: 48 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const allValues = payload.series.flatMap((item) => item.values)
    .filter((value) => value !== null && value !== undefined)
    .map(Number);
  const upper = max(allValues) || 1;
  const indices = payload.categories.map((_, index) => String(index));
  const x = scalePoint().domain(indices).range([0, innerWidth]).padding(0.12);
  const y = scaleLinear().domain([0, upper]).nice().range([innerHeight, 0]);
  const svg = select(host).append("svg")
    .attr("viewBox", [0, 0, width, height]).attr("width", "100%").attr("height", height)
    .attr("role", "img").attr("aria-label", "Preisentwicklung für Bezug und Einspeisung");
  const plot = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
  plot.append("g").attr("class", "grid")
    .call(axisLeft(y).ticks(5).tickSize(-innerWidth).tickFormat(""));
  plot.append("g").attr("class", "axis")
    .call(axisLeft(y).ticks(5).tickFormat((value) => new Intl.NumberFormat("de-AT", { maximumFractionDigits: 1 }).format(value)));
  const maxTicks = Math.max(3, Math.floor(innerWidth / 68));
  const tickStep = Math.max(1, Math.ceil(indices.length / maxTicks));
  plot.append("g").attr("class", "axis").attr("transform", `translate(0,${innerHeight})`)
    .call(axisBottom(x).tickValues(indices.filter((_, index) => index % tickStep === 0))
      .tickFormat((index) => payload.categories[Number(index)]?.label || ""));
  const shape = line()
    .defined((point) => point.value !== null && point.value !== undefined)
    .x((point) => x(String(point.index)))
    .y((point) => y(Number(point.value)))
    .curve(curveMonotoneX);
  payload.series.forEach((item) => {
    const points = item.values.map((value, index) => ({ value, index }));
    plot.append("path").datum(points).attr("class", "price-line")
      .attr("d", shape).attr("stroke", item.color).attr("fill", "none");
    plot.selectAll(`.point-${item.label.replace(/\W/g, "")}`).data(points.filter((point) => point.value !== null))
      .join("circle").attr("cx", (point) => x(String(point.index)))
      .attr("cy", (point) => y(Number(point.value))).attr("r", 4)
      .attr("fill", item.color).attr("stroke", "white").attr("stroke-width", 1.5)
      .on("click", (_, point) => detail(host, payload, point.index));
  });
  legend(host, payload.series);
  if (payload.categories.length) detail(host, payload, payload.categories.length - 1);
}

function render(payload) {
  const host = document.getElementById("chart");
  if (!host) return;
  host.replaceChildren();
  host.style.minHeight = payload.kind === "bars" ? "260px" : "0";
  if (payload.kind === "donuts") renderDonuts(host, payload);
  else if (payload.kind === "lines") renderLines(host, payload);
  else renderBars(host, payload);
}

window.renderEEGD3Chart = render;
