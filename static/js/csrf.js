/* Proteção CSRF no navegador.
 *
 * O token vem da <meta name="csrf-token"> do base.html. Este script:
 *  1. envia o token no cabeçalho X-CSRF-Token em todo fetch que altera dados
 *     (POST, PUT, PATCH, DELETE) para o mesmo domínio;
 *  2. coloca o campo oculto csrf_token em todo <form method="post"> do mesmo
 *     domínio, inclusive os criados dinamicamente pelo JavaScript das páginas.
 * O servidor (app.py) recusa com HTTP 400 quem não enviar o token correto.
 */
(function () {
  "use strict";

  var meta = document.querySelector('meta[name="csrf-token"]');
  var token = meta ? meta.getAttribute("content") : "";
  if (!token) return;

  var SAFE = /^(GET|HEAD|OPTIONS)$/i;

  function sameOrigin(url) {
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch (e) {
      return false;
    }
  }

  /* 1) fetch */
  var nativeFetch = window.fetch;
  if (nativeFetch) {
    window.fetch = function (input, init) {
      var isRequest = typeof Request !== "undefined" && input instanceof Request;
      var method = (init && init.method) || (isRequest ? input.method : "GET");
      var url = isRequest ? input.url : String(input);

      if (!SAFE.test(method) && sameOrigin(url)) {
        var headers = new Headers(
          (init && init.headers) || (isRequest ? input.headers : undefined)
        );
        if (!headers.has("X-CSRF-Token")) headers.set("X-CSRF-Token", token);
        init = Object.assign({}, init, { headers: headers });
      }
      return nativeFetch.call(this, input, init);
    };
  }

  /* 2) formulários */
  function addToken(form) {
    if (SAFE.test(form.getAttribute("method") || "get")) return;
    if (!sameOrigin(form.getAttribute("action") || window.location.href)) return;

    var field = form.querySelector('input[name="csrf_token"]');
    if (!field) {
      field = document.createElement("input");
      field.type = "hidden";
      field.name = "csrf_token";
      form.appendChild(field);
    }
    field.value = token;
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form").forEach(addToken);
  });

  // Captura o envio antes dos handlers da página, que podem ler new FormData(form).
  document.addEventListener(
    "submit",
    function (event) {
      if (event.target && event.target.tagName === "FORM") addToken(event.target);
    },
    true
  );
})();
