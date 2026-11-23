document.addEventListener("DOMContentLoaded", function () {
    const geojsonUrl = document.getElementById("mapaBrasil")?.dataset.geojsonUrl;

    // =========================================

    // EVOLUÇÃO MENSAL

    // =========================================

    const dadosElement = document.getElementById(

        "dadosEvolucao"

    );

    const evolucao = JSON.parse(

        dadosElement.textContent

    );

    const labels = evolucao.map(

        item => item.year_month

    );

    const valores = evolucao.map(

        item => item.negotiated_value

    );

    const quantidade = evolucao.map(

        item => item.freight_count

    );

    const canvas = document.getElementById(

        "evolucaoMensal"

    );

    if (canvas && typeof Chart !== "undefined") {

        new Chart(canvas, {

            type: "line",

            data: {

                labels: labels,

                datasets: [

                    {

                        label: "Valor negociado",

                        data: valores,

                        tension: 0.3,

                        fill: false,

                        yAxisID: "y"

                    },

                    {

                        label: "Quantidade de fretes",

                        data: quantidade,

                        tension: 0.3,

                        fill: false,

                        yAxisID: "y2"

                    }

                ]

            },

            options: {

                responsive: true,

                interaction: {

                    mode: "index",

                    intersect: false

                },

                maintainAspectRatio: false,

                plugins: {

                    tooltip: {

                        callbacks: {

                            label: function (context) {

                                const valor = Number(

                                    context.raw || 0

                                );

                                if (

                                    context.dataset.label ===

                                    "Valor negociado"

                                ) {

                                    return "R$ " +

                                        valor.toLocaleString(

                                            "pt-BR",

                                            {

                                                minimumFractionDigits: 2,

                                                maximumFractionDigits: 2

                                            }

                                        );

                                }

                                return valor.toLocaleString(

                                    "pt-BR"

                                );

                            }

                        }

                    }

                },

                scales: {

                    y: {

                        type: "linear",

                        position: "left",

                        ticks: {

                            callback: function (value) {

                                return "R$ " +

                                    Number(value).toLocaleString(

                                        "pt-BR",

                                        {

                                            notation: "compact",

                                            maximumFractionDigits: 1

                                        }

                                    );

                            }

                        }

                    },

                    y2: {

                        type: "linear",

                        position: "right",

                        display: true,

                        grid: {

                            drawOnChartArea: false

                        },

                        ticks: {

                            precision: 0

                        }

                    }

                }

            }

        });

    }

    // =========================================

    // DADOS REGIONAIS

    // =========================================

    const dadosEstadosElement = document.getElementById(

        "dadosEstados"

    );

    const dadosEstados = JSON.parse(

        dadosEstadosElement.textContent

    );

    const dadosPorEstado = {};

    dadosEstados.forEach(item => {

        const regiao = String(

            item.customer_region || ""

        );

        const uf = regiao

            .split(/[\\/]/)

            .pop()

            .trim()

            .toUpperCase();

        if (uf) {

            dadosPorEstado[uf] = item;

        }

    });

    // =========================================

    // MAPA DO BRASIL

    // =========================================

    if (typeof L === "undefined") {

        console.error(

            "Leaflet não foi carregado."

        );

        return;

    }

    const mapa = L.map("mapaBrasil", {

        zoomControl: true,

        attributionControl: false

    });

    mapa.setView(

        [-14.2, -51.9],

        4

    );

    // =========================================

    // CORES DOS ESTADOS

    // =========================================

    function obterCor(valor) {

        valor = Number(valor || 0);

        if (valor > 20000000) {

            return "#08306b";

        }

        if (valor > 10000000) {

            return "#2171b5";

        }

        if (valor > 5000000) {

            return "#4292c6";

        }

        if (valor > 1000000) {

            return "#6baed6";

        }

        if (valor > 100000) {

            return "#9ecae1";

        }

        return "#c6dbef";

    }

    // =========================================

    // FORMATAÇÃO DE MOEDA

    // =========================================

    function formatarMoeda(valor) {

        return Number(valor || 0).toLocaleString(

            "pt-BR",

            {

                style: "currency",

                currency: "BRL"

            }

        );

    }

    // =========================================

    // IDENTIFICA UF NO GEOJSON

    // =========================================

    function obterUF(feature) {

        const properties = feature.properties || {};

        let uf =

            properties.sigla ||

            properties.SIGLA ||

            properties.uf ||

            properties.UF ||

            properties.abbrev ||

            properties.abbreviation;

        if (!uf) {

            return "";

        }

        return String(uf)

            .replace("BR/", "")

            .trim()

            .toUpperCase();

    }

    // =========================================

    // ESTILO DOS ESTADOS

    // =========================================

    function estiloEstado(feature) {

        const uf = obterUF(feature);

        const estado = dadosPorEstado[uf];

        const valor = estado

            ? Number(estado.negotiated_value || 0)

            : 0;

        return {

            fillColor: obterCor(valor),

            weight: 1,

            opacity: 1,

            color: "#ffffff",

            fillOpacity: 0.8

        };

    }

    // =========================================

    // GEOJSON DO BRASIL

    // =========================================

    fetch(

        geojsonUrl

    )

    .then(response => {

        if (!response.ok) {

            throw new Error(

                "Não foi possível carregar estados.geojson"

            );

        }

        return response.json();

    })

    .then(geojson => {

        L.geoJSON(geojson, {

            style: estiloEstado,

            onEachFeature: function (feature, layer) {

                const uf = obterUF(feature);

                const estado = dadosPorEstado[uf];

                const sla = (

                    estado && estado.sla != null

                )

                    ? `${(

                        Number(estado.sla) * 100

                    ).toFixed(1).replace(".", ",")}%`

                    : "N/A";

                const nome =

                    feature.properties.nome ||

                    feature.properties.NOME ||

                    feature.properties.name ||

                    uf;

                // =====================================

                // TOOLTIP DOS ESTADOS

                // =====================================

                if (estado) {

                    const conteudo = document.createElement("div");

                    conteudo.style.minWidth = "190px";

                    const titulo = document.createElement("strong");

                    titulo.style.fontSize = "15px";

                    titulo.textContent = `${nome} (${uf})`;

                    conteudo.appendChild(titulo);

                    const linha = document.createElement("hr");

                    linha.style.margin = "7px 0";

                    conteudo.appendChild(linha);

                    const campos = [

                        [

                            "Valor negociado",

                            formatarMoeda(estado.negotiated_value)

                        ],

                        [

                            "Fretes",

                            Number(

                                estado.freight_count || 0

                            ).toLocaleString("pt-BR")

                        ],

                        [

                            "Clientes",

                            Number(

                                estado.clientes || 0

                            ).toLocaleString("pt-BR")

                        ],

                        [

                            "SLA",

                            sla

                        ]

                    ];

                    campos.forEach(([rotulo, valor]) => {

                        const item = document.createElement("div");

                        item.style.marginBottom = "5px";

                        const texto = document.createElement("strong");

                        texto.textContent = `${rotulo}: `;

                        item.appendChild(texto);

                        item.appendChild(

                            document.createTextNode(valor)

                        );

                        conteudo.appendChild(item);

                    });

                    layer.bindTooltip(conteudo, {

                        sticky: true,

                        direction: "top"

                    });

                } else {

                    const conteudo = document.createElement("div");

                    const titulo = document.createElement("strong");

                    titulo.textContent = `${nome} (${uf})`;

                    conteudo.appendChild(titulo);

                    conteudo.appendChild(

                        document.createTextNode(" — Sem dados")

                    );

                    layer.bindTooltip(conteudo, {

                        sticky: true

                    });

                }

                // =====================================

                // HOVER DOS ESTADOS

                // =====================================

                layer.on({

                    mouseover: function (e) {

                        e.target.setStyle({

                            weight: 2,

                            color: "#333",

                            fillOpacity: 1

                        });

                        e.target.bringToFront();

                    },

                    mouseout: function (e) {

                        e.target.setStyle(

                            estiloEstado(feature)

                        );

                    }

                });

            }

        }).addTo(mapa);

        setTimeout(function () {

            mapa.invalidateSize();

        }, 100);

    })

    .catch(error => {

        console.error(

            "Erro ao carregar mapa:",

            error

        );

    });

});
