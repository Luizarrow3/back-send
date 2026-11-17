export function mountTerminal(onCommand) {
    const form = document.querySelector("#terminal-form");
    const input = document.querySelector("#terminal-input");
    const output = document.querySelector("#terminal-output");
    if (!form || !input || !output) return;

    const write = (text, kind = "result") => {
        const line = document.createElement("p");
        line.className = `terminal-${kind}`;
        line.textContent = text;
        output.append(line);
        output.scrollTop = output.scrollHeight;
    };

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const command = input.value.trim();
        if (!command) return;
        write(`admin@censo:~$ ${command}`, "command");
        input.value = "";
        try {
            const result = await onCommand(command);
            if (result) write(result);
        } catch (error) {
            write(error.message || "Não foi possível executar o comando.", "error");
        }
    });

    return { write };
}
