// --------------------------------------------------
// DADOS FICTÍCIOS PARA TESTES
// --------------------------------------------------

const dadosCliente = {

    nome: "Empresa Alpha Ltda",

    lancamentos: [

        {
            nf: "100001",
            dataLancamento: "01/08/2026",
            dataVencimento: "10/08/2026",
            dataPagamento: "09/08/2026",
            historico: "Pagamento realizado"
        },

        {
            nf: "100002",
            dataLancamento: "03/08/2026",
            dataVencimento: "13/08/2026",
            dataPagamento: "—",
            historico: "Aguardando pagamento"
        },

        {
            nf: "100003",
            dataLancamento: "05/08/2026",
            dataVencimento: "15/08/2026",
            dataPagamento: "14/08/2026",
            historico: "Pagamento realizado"
        },

        {
            nf: "100004",
            dataLancamento: "08/08/2026",
            dataVencimento: "18/08/2026",
            dataPagamento: "—",
            historico: "NF emitida"
        },

        {
            nf: "100005",
            dataLancamento: "10/08/2026",
            dataVencimento: "20/08/2026",
            dataPagamento: "—",
            historico: "Em aberto"
        }

    ]
};


// --------------------------------------------------
// ELEMENTOS DA PÁGINA
// --------------------------------------------------

const nomeCliente = document.getElementById("nome-cliente");

const tipoPesquisa = document.getElementById("tipo-pesquisa");

const valorPesquisa = document.getElementById("valor-pesquisa");

const quantidadeResultados = document.getElementById(
    "quantidade-resultados"
);

const tabelaResultados = document.getElementById(
    "tabela-resultados"
);

const botaoVoltar = document.getElementById("btn-voltar");


// --------------------------------------------------
// OBTÉM OS DADOS DA PESQUISA
// --------------------------------------------------

const parametros = new URLSearchParams(
    window.location.search
);

const tipo = parametros.get("tipo");

const valor = parametros.get("valor");


// --------------------------------------------------
// MOSTRA O NOME DO CLIENTE
// --------------------------------------------------

nomeCliente.textContent = dadosCliente.nome;


// --------------------------------------------------
// MOSTRA COMO A PESQUISA FOI REALIZADA
// --------------------------------------------------

if (tipo === "cnpj") {

    tipoPesquisa.textContent =
        "Pesquisa realizada por CNPJ";

} else if (tipo === "id") {

    tipoPesquisa.textContent =
        "Pesquisa realizada por ID do Cliente";

} else {

    tipoPesquisa.textContent =
        "Pesquisa realizada";

}


// --------------------------------------------------
// MOSTRA O VALOR PESQUISADO
// --------------------------------------------------

if (valor) {

    valorPesquisa.textContent = valor;

} else {

    valorPesquisa.textContent = "Não informado";

}


// --------------------------------------------------
// MOSTRA A QUANTIDADE DE RESULTADOS
// --------------------------------------------------

const quantidade = dadosCliente.lancamentos.length;

quantidadeResultados.textContent =
    `${quantidade} ${quantidade === 1 ? "registro" : "registros"}`;


// --------------------------------------------------
// PREENCHE A TABELA
// --------------------------------------------------

dadosCliente.lancamentos.forEach(function (lancamento) {

    const linha = document.createElement("tr");

    linha.innerHTML = `
        <td>${lancamento.nf}</td>

        <td>${lancamento.dataLancamento}</td>

        <td>${lancamento.dataVencimento}</td>

        <td>${lancamento.dataPagamento}</td>

        <td>${lancamento.historico}</td>
    `;

    tabelaResultados.appendChild(linha);

});


// --------------------------------------------------
// BOTÃO VOLTAR
// --------------------------------------------------

botaoVoltar.addEventListener("click", function () {

    window.location.href = "busca.html";

});