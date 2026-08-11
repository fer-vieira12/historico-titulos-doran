const campoCnpj = document.getElementById("cnpj");
const botaoBuscar = document.getElementById("btn-buscar");


// --------------------------------------------------
// MÁSCARA DO CNPJ
// --------------------------------------------------

campoCnpj.addEventListener("input", function () {

    let valor = campoCnpj.value;

    // Remove tudo que não for número
    valor = valor.replace(/\D/g, "");

    // Limita o CNPJ a 14 números
    valor = valor.slice(0, 14);

    // Aplica a máscara progressivamente
    if (valor.length > 12) {

        valor = valor.replace(
            /^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2}).*/,
            "$1.$2.$3/$4-$5"
        );

    } else if (valor.length > 8) {

        valor = valor.replace(
            /^(\d{2})(\d{3})(\d{3})(\d{0,4}).*/,
            "$1.$2.$3/$4"
        );

    } else if (valor.length > 5) {

        valor = valor.replace(
            /^(\d{2})(\d{3})(\d{0,3}).*/,
            "$1.$2.$3"
        );

    } else if (valor.length > 2) {

        valor = valor.replace(
            /^(\d{2})(\d{0,3}).*/,
            "$1.$2"
        );
    }

    // Atualiza o campo
    campoCnpj.value = valor;

});


// --------------------------------------------------
// BOTÃO BUSCAR
// --------------------------------------------------

botaoBuscar.addEventListener("click", function () {

    const campoId = document.getElementById("cliente-id");

    const cnpj = campoCnpj.value.trim();

    const idCliente = campoId.value.trim();


    // Se o CNPJ tiver algum valor,
    // vamos utilizá-lo na pesquisa.

    if (cnpj !== "") {

        const url =
            `cliente.html?tipo=cnpj&valor=${encodeURIComponent(cnpj)}`;

        window.location.href = url;

        return;
    }


    // Caso contrário, utilizamos o ID.

    if (idCliente !== "") {

        const url =
            `cliente.html?tipo=id&valor=${encodeURIComponent(idCliente)}`;

        window.location.href = url;

        return;
    }


    // Por enquanto não faremos validação.
    // Apenas mantemos o comportamento silencioso
    // caso nenhum campo tenha sido preenchido.

});